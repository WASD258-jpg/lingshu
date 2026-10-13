# -*- coding: utf-8 -*-
"""test_time_anchor · 相对时间锚定守卫（LINGSHU_TIME_ANCHOR=1，默认关闭）

契约：节点内容里的相对 / 显式时间表达，以节点 temporal_coordinate 所在日为参照归一成
事件区间（派生表 nodes_when）；问句点名日期时，区间有交集的节点按区间内相关度排在最前，
余位按原排序补齐。

判据：
  · 默认关闭：enabled() 为假，不建触发器，点名日期的问句结果与改前逐位相同；
  · 规则表：英文 / 中文常见相对写法在固定参照日下解析成确定区间；无时间表达 → None；
  · 证据写「yesterday / 昨天」、说话日为 5 月 8 日，问「2023年5月7日 / 7 May 2023」→ top-1；
  · LIKE 路径与 FTS 路径都生效；
  · 无日期问句：开关开 / 关结果逐位相同；
  · 内容更新 → 区间重算；节点删除 → 区间移除（触发器 + 脏队列）；
  · 开关关闭 → 拆触发器、清派生表；
  · LINGSHU_TIME_ANCHOR_TZ：同一 UNIX 时刻在 UTC+8 下参照日顺延。

变异哨兵：把 _time_rerank 首个判断后直接 `return results`，test_date_query_pulls_event 必红；
把 WhenIndex.sync 里的 resolve(...) 换成 None（只按说话当日），test_date_query_pulls_event 必红；
把 last_wd 的 `or 7` 去掉（「last Tuesday」在周二说成当天），test_rules 必红；
删掉 nodes_when_au 触发器，test_update_and_delete_resync 必红。
"""
import datetime as dt
import time

import pytest

from lingshu.core import timeanchor as T
from lingshu.core.core import SpacetimeMemoryEngine

pytestmark = pytest.mark.filterwarnings("ignore")

D = dt.date
REF = D(2023, 7, 20)  # 周四


def _ts(y, m, d, h=12):
    return (dt.datetime(y, m, d, h) - dt.datetime(1970, 1, 1)).total_seconds()


@pytest.mark.parametrize("text,want", [
    ("I joined a new group last Tues.", (D(2023, 7, 18),) * 2),
    ("Yesterday was crazy", (D(2023, 7, 19),) * 2),
    ("the day before yesterday", (D(2023, 7, 18),) * 2),
    ("We went biking last weekend", (D(2023, 7, 15), D(2023, 7, 16))),
    ("Started hitting the gym last week", (D(2023, 7, 13), D(2023, 7, 19))),
    ("I took this picture last month", (D(2023, 6, 1), D(2023, 6, 30))),
    ("my trip last year", (D(2022, 1, 1), D(2022, 12, 31))),
    ("camping last summer", (D(2022, 6, 1), D(2022, 8, 31))),
    ("I started two years ago", (D(2021, 1, 1), D(2021, 12, 31))),
    ("my album dropped on the 11th", (D(2023, 7, 11),) * 2),
    ("met in August last year", (D(2022, 8, 1), D(2022, 8, 31))),
    ("昨天去了公园", (D(2023, 7, 19),) * 2),
    ("上周二加入了一个团体", (D(2023, 7, 18),) * 2),
    ("上周末去骑车", (D(2023, 7, 15), D(2023, 7, 16))),
    ("三天前", (D(2023, 7, 17),) * 2),
    ("上个月拍的", (D(2023, 6, 1), D(2023, 6, 30))),
    ("去年夏天", (D(2022, 6, 1), D(2022, 8, 31))),
    ("5月7日那天", (D(2023, 5, 7),) * 2),
    ("下周三见", (D(2023, 7, 26),) * 2),
    ("2023年5月7日", (D(2023, 5, 7),) * 2),
    ("on 7 May 2023", (D(2023, 5, 7),) * 2),
    ("今天天气不错", (REF, REF)),
    ("没有任何时间词", None),
    ("I love painting", None),
])
def test_rules(text, want):
    assert T.resolve(text, REF) == want


def test_rules_tuesday_on_tuesday():
    # 周二说「last Tuesday」是上周二，不是当天
    assert T.resolve("last Tuesday", D(2023, 7, 18)) == (D(2023, 7, 11),) * 2


@pytest.mark.parametrize("q,want", [
    ("Caroline 2023年5月7日", (D(2023, 5, 7),) * 2),
    ("What did Caroline do on May 7, 2023", (D(2023, 5, 7),) * 2),
    ("Caroline May 2023", (D(2023, 5, 1), D(2023, 5, 31))),
    ("2023-05", (D(2023, 5, 1), D(2023, 5, 31))),
    ("Caroline 喜欢什么", None),
])
def test_parse_query(q, want):
    assert T.parse_query(q, ref=REF) == want


EVENT = "Caroline: I went to a LGBTQ support group yesterday and it was so powerful."
NOISE = ["Caroline: Painting is how I express myself.",
         "Caroline: The pottery class was so much fun, 2023 has been a good year.",
         "Melanie: My kids love the beach.",
         "Caroline: I'm so thankful for my friends and mentors.",
         "Caroline: Let's catch up again soon!"]


def _build(tmp_path, monkeypatch):
    e = SpacetimeMemoryEngine(str(tmp_path / "e.db"))
    ids = {}
    real = time.time
    plan = [(EVENT, _ts(2023, 5, 8))] + [(t, _ts(2023, 6, 1 + i)) for i, t in enumerate(NOISE)]
    for text, ts in plan:
        monkeypatch.setattr(time, "time", lambda v=ts: v)
        ids[e.add_perception(text, skip_dedup=True).id] = "event" if text == EVENT else "noise"
    monkeypatch.setattr(time, "time", real)
    return e, ids


@pytest.fixture(params=["like", "fts"])
def path(request, monkeypatch):
    monkeypatch.delenv("LINGSHU_TIME_ANCHOR", raising=False)
    monkeypatch.delenv("LINGSHU_TIME_ANCHOR_TZ", raising=False)
    if request.param == "fts":
        monkeypatch.setenv("LINGSHU_FTS", "1")
    else:
        monkeypatch.delenv("LINGSHU_FTS", raising=False)
    return request.param


def test_default_off(tmp_path, monkeypatch):
    monkeypatch.delenv("LINGSHU_TIME_ANCHOR", raising=False)
    assert not T.enabled()
    e = SpacetimeMemoryEngine(str(tmp_path / "e.db"))
    trig = [r[0] for r in e.store.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'nodes_when_%'")]
    assert trig == []


@pytest.mark.parametrize("q", ["Caroline 2023年5月7日", "Caroline 7 May 2023"])
def test_date_query_pulls_event(tmp_path, path, monkeypatch, q):
    e, ids = _build(tmp_path, monkeypatch)
    off = [ids[n.id] for n, _ in e.store.search_content(q, limit=3)]
    assert off[:1] != ["event"]  # 改前：证据写 yesterday，字面与时间戳都对不上
    monkeypatch.setenv("LINGSHU_TIME_ANCHOR", "1")
    assert [ids[n.id] for n, _ in e.store.search_content(q, limit=3)][:1] == ["event"]


def test_no_date_unchanged(tmp_path, path, monkeypatch):
    e, ids = _build(tmp_path, monkeypatch)
    q = "Caroline support group"
    off = [n.id for n, _ in e.store.search_content(q, limit=5)]
    monkeypatch.setenv("LINGSHU_TIME_ANCHOR", "1")
    assert [n.id for n, _ in e.store.search_content(q, limit=5)] == off


def _iv(e, nid):
    e.store._when.sync()
    r = e.store.conn.execute("SELECT d0, d1 FROM nodes_when WHERE nid=?", (nid,)).fetchone()
    return None if r is None else (D.fromordinal(r[0]), D.fromordinal(r[1]))


def test_update_and_delete_resync(tmp_path, monkeypatch):
    monkeypatch.setenv("LINGSHU_TIME_ANCHOR", "1")
    monkeypatch.delenv("LINGSHU_TIME_ANCHOR_TZ", raising=False)
    e, ids = _build(tmp_path, monkeypatch)
    nid = next(k for k, v in ids.items() if v == "event")
    assert _iv(e, nid) == (D(2023, 5, 7),) * 2
    e.store.conn.execute("UPDATE nodes SET content=? WHERE id=?", ("Caroline: went there last weekend", nid))
    e.store.conn.commit()
    assert _iv(e, nid) == (D(2023, 5, 6), D(2023, 5, 7))  # 5 月 8 日周一：刚过去的周末
    e.store.conn.execute("DELETE FROM nodes WHERE id=?", (nid,))
    e.store.conn.commit()
    assert _iv(e, nid) is None


def test_detach_on_flag_off(tmp_path, monkeypatch):
    monkeypatch.setenv("LINGSHU_TIME_ANCHOR", "1")
    db = str(tmp_path / "e.db")
    e = SpacetimeMemoryEngine(db)
    e.add_perception("yesterday was fun", skip_dedup=True)
    del e
    monkeypatch.delenv("LINGSHU_TIME_ANCHOR")
    e2 = SpacetimeMemoryEngine(db)
    c = e2.store.conn
    assert [r[0] for r in c.execute(
        "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'nodes_when_%'")] == []
    assert c.execute("SELECT COUNT(*) FROM nodes_when").fetchone()[0] == 0


def test_tz_offset(monkeypatch):
    ts = _ts(2023, 5, 7, 20)  # UTC 20:00
    monkeypatch.delenv("LINGSHU_TIME_ANCHOR_TZ", raising=False)
    assert T.ts_to_date(ts) == D(2023, 5, 7)
    monkeypatch.setenv("LINGSHU_TIME_ANCHOR_TZ", "8")
    assert T.ts_to_date(ts) == D(2023, 5, 8)
