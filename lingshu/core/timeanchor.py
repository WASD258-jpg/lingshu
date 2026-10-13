"""相对时间锚定（LINGSHU_TIME_ANCHOR=1；默认关闭，与 LINGSHU_FTS / LINGSHU_ANCHOR 独立）。

问题：对话记忆里事件时间几乎总是相对写法——「昨天」「上周二」「last weekend」「two years ago」。
节点只记录了「说这句话的时刻」（temporal_coordinate），没有记录「事情发生的时刻」。于是
「5 月 7 日 Caroline 做了什么」这类按日期点名的问句，字面检索与按 temporal_coordinate 过滤
都落空：证据里写的是 yesterday，说话时刻是 5 月 8 日。

做法（全部确定性，零 LLM，D-005）：
- 写入侧（派生索引，不改 nodes 行）：节点内容里的相对 / 显式时间表达，以该节点
  temporal_coordinate 所在日为参照，归一成闭区间 [d0, d1]（公历日序号），写入派生表
  ``nodes_when``；内容里没有可解析的时间表达 → 区间取说话当日（与「按时间戳过滤」同口径）。
  规则解析不了的写法不猜，按说话当日处理。
- 查询侧：问句里的日期（2023年5月7日 / 2023-05-07 / 7 May 2023 / May 2023 / 上周二 …）
  解析成区间 → 区间有交集的节点按区间内相关度排在最前，不足 limit 用原排序补齐。
  问句里没有日期 → 原路径逐位不变。

参照日的时区：temporal_coordinate 是 UNIX 秒，按 ``LINGSHU_TIME_ANCHOR_TZ``（相对 UTC 的
小时数，缺省 0）换算成日历日；查询中的相对表达以「当前时刻」为参照，可显式传 ref_date。

已知边界（见 docs/plans/相对时间锚定_设计_v0.1.md）：只认规则表里的写法；「上周」一律取
参照日前 7 天的滚动窗口而非日历周；年份缺省的「5月7日」取不晚于参照日的最近一次。
"""
from __future__ import annotations

import datetime as _dt
import os
import re
import sqlite3
from typing import List, Optional, Sequence, Tuple

FLAG = "LINGSHU_TIME_ANCHOR"
TZ_FLAG = "LINGSHU_TIME_ANCHOR_TZ"
Interval = Tuple[_dt.date, _dt.date]
_D = _dt.date
_TD = _dt.timedelta

MAX_CANDIDATES = 5000  # 宽区间（「2023年」）时容器内候选上限；按区间窄者优先取


def enabled() -> bool:
    return os.environ.get(FLAG, "").strip() == "1"


def _tz_hours() -> float:
    try:
        return float(os.environ.get(TZ_FLAG, "0") or 0)
    except ValueError:
        return 0.0


def ts_to_date(ts: Optional[float]) -> Optional[_dt.date]:
    if ts is None:
        return None
    try:
        return (_dt.datetime(1970, 1, 1) + _TD(seconds=float(ts) + 3600.0 * _tz_hours())).date()
    except (OverflowError, ValueError, TypeError):
        return None


# ---------------------------------------------------------------- 日历工具
def month_iv(y: int, m: int) -> Interval:
    s = _D(y, m, 1)
    e = (_D(y + 1, 1, 1) if m == 12 else _D(y, m + 1, 1)) - _TD(1)
    return (s, e)


def year_iv(y: int) -> Interval:
    return (_D(y, 1, 1), _D(y, 12, 31))


def shift_month(d: _dt.date, n: int) -> Tuple[int, int]:
    m = d.month - 1 + n
    return d.year + m // 12, m % 12 + 1


def week_before(d: _dt.date) -> Interval:
    return (d - _TD(7), d - _TD(1))


def weekend_before(d: _dt.date) -> Interval:
    """严格早于 d 所在周的最近一个周末（周六、周日）。"""
    wd = d.weekday()
    sat = d - _TD(8) if wd == 6 else d - _TD(7) if wd == 5 else d - _TD(wd + 2)
    return (sat, sat + _TD(1))


def this_weekend(d: _dt.date) -> Interval:
    """周一、周二说「这个周末」多指刚过去的；周六日指当周；周三至周五指即将到来的。"""
    wd = d.weekday()
    if wd <= 1:
        return weekend_before(d)
    sat = d - _TD(wd - 5) if wd >= 5 else d + _TD(5 - wd)
    return (sat, sat + _TD(1))


def next_weekend(d: _dt.date) -> Interval:
    """下一个日历周的周六、周日。"""
    sat = d - _TD(d.weekday()) + _TD(12)
    return (sat, sat + _TD(1))


def last_wd(d: _dt.date, w: int) -> Interval:
    x = d - _TD((d.weekday() - w) % 7 or 7)
    return (x, x)


def next_wd(d: _dt.date, w: int) -> Interval:
    x = d + _TD((w - d.weekday()) % 7 or 7)
    return (x, x)


def ago(d: _dt.date, n: int, unit: str) -> Interval:
    if unit == "day":
        x = d - _TD(n)
        return (x, x)
    if unit == "week":
        x = d - _TD(7 * n)
        return (x - _TD(3), x + _TD(3))
    if unit == "month":
        return month_iv(*shift_month(d, -n))
    return year_iv(d.year - n)


def season_iv(d: _dt.date, s: str, n: int) -> Interval:
    """n=-1：参照日之前最近一个已结束的该季节；n=0：参照年的该季节。北半球气象季节。"""
    s = {"autumn": "fall", "春": "spring", "夏": "summer", "秋": "fall", "冬": "winter"}.get(s, s)
    rng = {"spring": (3, 5), "summer": (6, 8), "fall": (9, 11)}
    if s == "winter":
        y = d.year if (n == 0 or d.month >= 3) else d.year - 1
        return (_D(y - 1, 12, 1), month_iv(y, 2)[1])
    a, b = rng[s]
    y = d.year
    if n < 0 and d.month <= b:
        y -= 1
    return (_D(y, a, 1), month_iv(y, b)[1])


def month_recent(d: _dt.date, m: int) -> Interval:
    return month_iv(d.year if m <= d.month else d.year - 1, m)


def day_recent(d: _dt.date, m: int, day: int) -> Optional[Interval]:
    for y in (d.year, d.year - 1):
        try:
            x = _D(y, m, day)
        except ValueError:
            return None
        if x <= d:
            return (x, x)
    return None


def nth_day(d: _dt.date, n: int) -> Optional[Interval]:
    if not 1 <= n <= 31:
        return None
    try:
        x = _D(d.year, d.month, n) if n <= d.day else _D(*shift_month(d, -1), n)
    except ValueError:
        return None
    return (x, x)


def _safe_date(y: int, m: int, d: int) -> Optional[_dt.date]:
    try:
        return _D(y, m, d)
    except ValueError:
        return None


# ---------------------------------------------------------------- 数词
_EN_MON = ["january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december"]
MON = {m: i + 1 for i, m in enumerate(_EN_MON)}
MON.update({m[:3]: i + 1 for i, m in enumerate(_EN_MON)})
MON["sept"] = 9
_MONP = r"(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sept?|oct|nov|dec)"
_EN_WD = {w: i for i, w in enumerate(["monday", "tuesday", "wednesday", "thursday", "friday",
                                       "saturday", "sunday"])}
_EN_WD.update({"mon": 0, "tue": 1, "tues": 1, "wed": 2, "thu": 3, "thur": 3, "thurs": 3,
               "fri": 4, "sat": 5, "sun": 6})
_WDP = r"(monday|tuesday|wednesday|thursday|friday|saturday|sunday|mon|tues?|wed|thu(?:rs?)?|fri|sat|sun)"
_EN_NUM = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
           "seven": 7, "eight": 8, "nine": 9, "ten": 10, "couple of": 2, "few": 3, "several": 3}
_ENNP = r"(\d+|a|an|one|two|three|four|five|six|seven|eight|nine|ten|couple of|few|several)"

_CN_DIG = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6,
           "七": 7, "八": 8, "九": 9}
_CNNP = r"([0-9]{1,4}|[零〇一二两三四五六七八九十百]{1,5}|几|半)"
_CN_WD = {"一": 0, "二": 1, "三": 2, "四": 3, "五": 4, "六": 5, "日": 6, "天": 6, "末": None}


def cn_num(s: str) -> Optional[int]:
    if s.isdigit():
        return int(s)
    if s == "几":
        return 3
    total, cur = 0, None
    for ch in s:
        if ch in _CN_DIG:
            cur = _CN_DIG[ch]
        elif ch in "十百":
            total += (1 if cur is None else cur) * (10 if ch == "十" else 100)
            cur = None
        else:
            return None
    total += cur or 0
    return total or None


def _en_n(s: str) -> int:
    return _EN_NUM.get(s) or int(s)


# ---------------------------------------------------------------- 规则表
# 每条：(编译正则, 构造函数(m, d) → 区间或 None)。多条命中时取在文本中最靠前者
# （「day before yesterday」先于其中的 yesterday；同位置按表序）。
def _r(p, flags=re.I):
    return re.compile(p, flags)


_UNIT_EN = r"(day|week|month|year)s?"
_CN_UNIT = {"天": "day", "日": "day", "周": "week", "星期": "week", "礼拜": "week",
            "个月": "month", "月": "month", "年": "year"}

RULES = [
    # ---- 英文
    (_r(r"\bday before yesterday\b"), lambda m, d: (d - _TD(2),) * 2),
    (_r(r"\byesterday\b|\blast night\b"), lambda m, d: (d - _TD(1),) * 2),
    (_r(r"\btomorrow\b"), lambda m, d: (d + _TD(1),) * 2),
    (_r(r"\b(?:last|past|this past) weekend\b"), lambda m, d: weekend_before(d)),
    (_r(r"\bthis weekend\b"), lambda m, d: this_weekend(d)),
    (_r(r"\b(?:last|past) week\b|\ba week ago\b"), lambda m, d: week_before(d)),
    (_r(r"\bnext week\b"), lambda m, d: (d + _TD(1), d + _TD(7))),
    (_r(r"\bnext month\b"), lambda m, d: month_iv(*shift_month(d, 1))),
    (_r(r"\blast month\b|\ba month ago\b"), lambda m, d: month_iv(*shift_month(d, -1))),
    (_r(r"\bthis month\b"), lambda m, d: month_iv(d.year, d.month)),
    (_r(_MONP + r" last year\b"), lambda m, d: month_iv(d.year - 1, MON[m.group(1)])),
    (_r(r"\blast year\b|\ba year ago\b"), lambda m, d: year_iv(d.year - 1)),
    (_r(r"\bthis year\b"), lambda m, d: year_iv(d.year)),
    (_r(r"\bnext year\b"), lambda m, d: year_iv(d.year + 1)),
    (_r(r"\blast (summer|winter|spring|fall|autumn)\b"), lambda m, d: season_iv(d, m.group(1).lower(), -1)),
    (_r(r"\b" + _ENNP + r" " + _UNIT_EN + r" ago\b"), lambda m, d: ago(d, _en_n(m.group(1).lower()), m.group(2).lower())),
    (_r(r"\bfor (?:about |almost |over |nearly )?" + _ENNP + r" " + _UNIT_EN + r"\b"),
     lambda m, d: ago(d, _en_n(m.group(1).lower()), m.group(2).lower())),
    (_r(r"\bnext " + _WDP + r"\b"), lambda m, d: next_wd(d, _EN_WD[m.group(1).lower()])),
    (_r(r"\b(?:last|on|this|this past) " + _WDP + r"\b"), lambda m, d: last_wd(d, _EN_WD[m.group(1).lower()])),
    (_r(r"\b(?:in|this|last) (january|february|march|april|june|july|august|september|october|november|december)\b"),
     lambda m, d: month_recent(d, MON[m.group(1).lower()])),
    (_r(r"\bon the (\d{1,2})(?:st|nd|rd|th)\b"), lambda m, d: nth_day(d, int(m.group(1)))),
    (_r(r"\bin (19\d\d|20\d\d)\b"), lambda m, d: year_iv(int(m.group(1)))),
    (_r(r"\btoday\b|\btonight\b|\bthis (?:morning|afternoon|evening)\b"), lambda m, d: (d, d)),
    # ---- 中文
    (_r(r"大前天"), lambda m, d: (d - _TD(3),) * 2),
    (_r(r"前天"), lambda m, d: (d - _TD(2),) * 2),
    (_r(r"昨天|昨晚|昨日|昨儿"), lambda m, d: (d - _TD(1),) * 2),
    (_r(r"大后天"), lambda m, d: (d + _TD(3),) * 2),
    (_r(r"后天"), lambda m, d: (d + _TD(2),) * 2),
    (_r(r"明天|明晚|明早|明日"), lambda m, d: (d + _TD(1),) * 2),
    (_r(r"今天|今晚|今早|今日|今儿|今天早上"), lambda m, d: (d, d)),
    (_r(r"(?:上|上个)(?:周|星期|礼拜)([一二三四五六日天末])"),
     lambda m, d: weekend_before(d) if m.group(1) == "末" else last_wd(d, _CN_WD[m.group(1)])),
    (_r(r"(?:下|下个)(?:周|星期|礼拜)([一二三四五六日天末])"),
     lambda m, d: next_weekend(d) if m.group(1) == "末" else next_wd(d + _TD(6 - d.weekday()), _CN_WD[m.group(1)])),
    (_r(r"(?:这|这个|本)(?:周|星期|礼拜)([一二三四五六日天末])"),
     lambda m, d: this_weekend(d) if m.group(1) == "末" else (lambda x: (x, x))(d - _TD(d.weekday()) + _TD(_CN_WD[m.group(1)]))),
    (_r(r"(?<![上下这本个])(?:周|星期|礼拜)([一二三四五六日天])"), lambda m, d: last_wd(d, _CN_WD[m.group(1)])),
    (_r(r"周末"), lambda m, d: this_weekend(d)),
    (_r(r"(?:上|上个)(?:周|星期|礼拜)"), lambda m, d: week_before(d)),
    (_r(r"(?:下|下个)(?:周|星期|礼拜)"), lambda m, d: (d + _TD(1), d + _TD(7))),
    (_r(r"上(?:个)?月"), lambda m, d: month_iv(*shift_month(d, -1))),
    (_r(r"下(?:个)?月"), lambda m, d: month_iv(*shift_month(d, 1))),
    (_r(r"(?:这|这个|本)月"), lambda m, d: month_iv(d.year, d.month)),
    (_r(r"去年(?:的)?([春夏秋冬])(?:天|季)"), lambda m, d: season_iv(_D(d.year - 1, 12, 31), m.group(1), 0) if m.group(1) != "冬" else season_iv(_D(d.year - 1, 12, 31), "冬", 0)),
    (_r(r"去年" + r"([0-9]{1,2}|[一二三四五六七八九十]{1,3})月"), lambda m, d: (lambda n: month_iv(d.year - 1, n) if n and n <= 12 else None)(cn_num(m.group(1)))),
    (_r(r"前年"), lambda m, d: year_iv(d.year - 2)),
    (_r(r"去年"), lambda m, d: year_iv(d.year - 1)),
    (_r(r"今年"), lambda m, d: year_iv(d.year)),
    (_r(r"明年"), lambda m, d: year_iv(d.year + 1)),
    (_r(r"(?:前几天|几天前|前些天|这几天)"), lambda m, d: (d - _TD(7), d - _TD(1))),
    (_r(_CNNP + r"\s*(天|日|周|星期|礼拜|个月|年)(?:以)?前"),
     lambda m, d: (lambda n: ago(d, n, _CN_UNIT[m.group(2)]) if n else None)(cn_num(m.group(1)) if m.group(1) != "半" else None)),
    (_r(r"(?<![0-9年])([0-9]{1,2}|[一二三四五六七八九十]{1,3})月([0-9]{1,2}|[一二三四五六七八九十]{1,3})(?:日|号)"),
     lambda m, d: (lambda a, b: day_recent(d, a, b) if a and b and a <= 12 else None)(cn_num(m.group(1)), cn_num(m.group(2)))),
    (_r(r"(?<![上下这本个0-9年])([0-9]{1,2})号"), lambda m, d: nth_day(d, int(m.group(1)))),
]

# 绝对日期（带年份）：写入与查询共用，优先级最高
_ABS = [
    (_r(r"((?:19|20)\d\d)-(\d{1,2})-(\d{1,2})"), lambda m: (lambda x: (x, x) if x else None)(_safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3))))),
    (_r(r"((?:19|20)\d\d)\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*[日号]"), lambda m: (lambda x: (x, x) if x else None)(_safe_date(int(m.group(1)), int(m.group(2)), int(m.group(3))))),
    (_r(r"\b(\d{1,2})(?:st|nd|rd|th)? " + _MONP + r",? ((?:19|20)\d\d)\b"), lambda m: (lambda x: (x, x) if x else None)(_safe_date(int(m.group(3)), MON[m.group(2).lower()], int(m.group(1))))),
    (_r(r"\b" + _MONP + r" (\d{1,2})(?:st|nd|rd|th)?,? ((?:19|20)\d\d)\b"), lambda m: (lambda x: (x, x) if x else None)(_safe_date(int(m.group(3)), MON[m.group(1).lower()], int(m.group(2))))),
    (_r(r"((?:19|20)\d\d)-(\d{1,2})(?![\d-])"), lambda m: month_iv(int(m.group(1)), int(m.group(2))) if 1 <= int(m.group(2)) <= 12 else None),
    (_r(r"((?:19|20)\d\d)\s*年\s*(\d{1,2})\s*月"), lambda m: month_iv(int(m.group(1)), int(m.group(2))) if 1 <= int(m.group(2)) <= 12 else None),
    (_r(r"\b" + _MONP + r",? ((?:19|20)\d\d)\b"), lambda m: month_iv(int(m.group(2)), MON[m.group(1).lower()])),
    (_r(r"((?:19|20)\d\d)\s*年"), lambda m: year_iv(int(m.group(1)))),
]


def _first(rules, text, *args):
    best = None
    for pat, f in rules:
        m = pat.search(text)
        if m is None:
            continue
        try:
            iv = f(m, *args)
        except (ValueError, KeyError, TypeError, OverflowError):
            iv = None
        if iv and (best is None or m.start() < best[0]):
            best = (m.start(), iv)
    return best[1] if best else None


def resolve(text: str, ref: _dt.date) -> Optional[Interval]:
    """内容中的时间表达 → 区间。先认带年份的绝对日期，再认相对表达；都没有 → None。"""
    if not text or ref is None:
        return None
    return _first(_ABS, text) or _first(RULES, text, ref)


def parse_query(q: str, ref: Optional[_dt.date] = None) -> Optional[Interval]:
    """问句中的日期 → 区间（绝对日期优先；相对表达以 ref 或今天为参照）。"""
    if not q:
        return None
    iv = _first(_ABS, q)
    if iv:
        return iv
    if ref is None:
        ref = ts_to_date(_dt.datetime.now(_dt.timezone.utc).timestamp())
    return _first(RULES, q, ref)


def to_ord(d: _dt.date) -> int:
    return d.toordinal()


# ---------------------------------------------------------------- 派生索引
_TRIGGERS = ("nodes_when_ai", "nodes_when_au", "nodes_when_ad")


class WhenIndex:
    """nodes_when(nid, d0, d1)：节点事件区间（公历日序号）。失败一律让调用方回退原路径。"""

    def __init__(self, store):
        self.store = store

    @classmethod
    def attach(cls, store) -> Optional["WhenIndex"]:
        try:
            with store._tx():
                c = store.conn
                c.execute("CREATE TABLE IF NOT EXISTS nodes_when "
                          "(nid TEXT PRIMARY KEY, d0 INTEGER, d1 INTEGER, src INTEGER)")
                c.execute("CREATE INDEX IF NOT EXISTS idx_nodes_when_d ON nodes_when(d0, d1)")
                c.execute("CREATE TABLE IF NOT EXISTS nodes_when_dirty (nid TEXT PRIMARY KEY)")
                c.execute("CREATE TRIGGER IF NOT EXISTS nodes_when_ai AFTER INSERT ON nodes "
                          "BEGIN INSERT OR IGNORE INTO nodes_when_dirty VALUES (new.id); END")
                c.execute("CREATE TRIGGER IF NOT EXISTS nodes_when_au AFTER UPDATE OF id, content, "
                          "temporal_coordinate ON nodes BEGIN "
                          "INSERT OR IGNORE INTO nodes_when_dirty VALUES (old.id); "
                          "INSERT OR IGNORE INTO nodes_when_dirty VALUES (new.id); END")
                c.execute("CREATE TRIGGER IF NOT EXISTS nodes_when_ad AFTER DELETE ON nodes "
                          "BEGIN INSERT OR IGNORE INTO nodes_when_dirty VALUES (old.id); END")
                c.execute("INSERT OR IGNORE INTO nodes_when_dirty "
                          "SELECT id FROM nodes WHERE id NOT IN (SELECT nid FROM nodes_when)")
            idx = cls(store)
            idx.sync()
            return idx
        except sqlite3.Error:
            return None

    @staticmethod
    def detach(store) -> None:
        """开关关闭：拆触发器、清派生表，保持默认写路径不变。"""
        try:
            c = store.conn
            have = {r[0] for r in c.execute(
                "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'nodes_when_%'")}
            if not have:
                return
            with store._tx():
                for t in _TRIGGERS:
                    c.execute(f"DROP TRIGGER IF EXISTS {t}")
                c.execute("DELETE FROM nodes_when")
                c.execute("DELETE FROM nodes_when_dirty")
        except sqlite3.Error:
            pass

    def sync(self, batch: int = 2000) -> int:
        store = self.store
        done = 0
        while True:
            c = store.conn
            ids = [r[0] for r in c.execute("SELECT nid FROM nodes_when_dirty LIMIT ?", (batch,))]
            if not ids:
                return done
            with store._tx():
                for nid in ids:
                    row = c.execute("SELECT content, temporal_coordinate FROM nodes WHERE id=?",
                                    (nid,)).fetchone()
                    c.execute("DELETE FROM nodes_when WHERE nid=?", (nid,))
                    if row is not None:
                        ref = ts_to_date(row[1])
                        if ref is not None:
                            iv = resolve(row[0] or "", ref)
                            src = 1 if iv else 0
                            iv = iv or (ref, ref)
                            c.execute("INSERT INTO nodes_when VALUES (?,?,?,?)",
                                      (nid, to_ord(iv[0]), to_ord(iv[1]), src))
                    c.execute("DELETE FROM nodes_when_dirty WHERE nid=?", (nid,))
                    done += 1

    def overlapping(self, iv: Interval, limit: int = MAX_CANDIDATES) -> List[str]:
        """与 iv 有交集的节点 id；区间窄者优先（越具体越先），同宽按 d0、nid 定序。"""
        self.sync()
        a, b = to_ord(iv[0]), to_ord(iv[1])
        rows = self.store.conn.execute(
            "SELECT nid FROM nodes_when WHERE d0 <= ? AND d1 >= ? "
            "ORDER BY (d1 - d0), d0, nid LIMIT ?", (b, a, limit)).fetchall()
        return [r[0] for r in rows]
