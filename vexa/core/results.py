"""Structured results every check returns.

Checks never return strings. They return Issues; the runner wraps them in a
CheckResult. The panel, "select problem", fixes and reports all read from these.
"""

from dataclasses import asdict, dataclass, field
from typing import List, Optional

# Status values, ordered from worst to best.
ERROR = "ERROR"
WARNING = "WARNING"
INFO = "INFO"
PASS = "PASS"

SEVERITIES = (ERROR, WARNING, INFO)
STATUS_ORDER = {ERROR: 0, WARNING: 1, INFO: 2, PASS: 3}


@dataclass
class Issue:
    """One problem found by a check.

    object_name: the object it was found on (None for scene-level issues).
    message:     plain-language description shown to the artist.
    value:       what was measured, e.g. "scale 2.0" or "23,410 tris".
    target:      what the preset expects, e.g. "1.0" or "20,000 tris".
    element:     "FACE", "EDGE" or "VERT" when specific mesh elements are affected.
    indices:     indices of those elements in object_name's mesh.
    no_fix:      why the check's fix leaves this issue alone, e.g. "has modifiers".
                 Set by the runner; empty when the fix can handle it.
    """

    object_name: Optional[str]
    message: str
    value: str = ""
    target: str = ""
    element: Optional[str] = None
    indices: List[int] = field(default_factory=list)
    no_fix: str = ""

    def to_dict(self) -> dict:
        d = asdict(self)
        d["count"] = len(self.indices)
        d.pop("indices")  # keep reports small; counts are enough
        return d


@dataclass
class CheckResult:
    """The outcome of one check in a preset run.

    fixable:  the check has a fix and at least one issue the fix can handle.
    fix_safe: that fix is safe, so Fix All runs it. Otherwise the artist confirms first.
    """

    check_id: str
    title: str
    status: str
    summary: str
    why: str = ""
    fixable: bool = False
    fix_safe: bool = False
    issues: List[Issue] = field(default_factory=list)
    size: float = 0.0  # how much is wrong; see runner.problem_size

    @property
    def objects(self) -> List[str]:
        names = []
        for issue in self.issues:
            if issue.object_name and issue.object_name not in names:
                names.append(issue.object_name)
        return names

    def to_dict(self) -> dict:
        return {
            "check": self.check_id,
            "title": self.title,
            "status": self.status,
            "summary": self.summary,
            "why": self.why,
            "fixable": self.fixable,
            "fix_safe": self.fix_safe,
            "issues": [i.to_dict() for i in self.issues],
        }


def summarize(issues: List[Issue], pass_text: str = "OK") -> str:
    """Short text for the results row."""
    if not issues:
        return pass_text
    if len(issues) == 1:
        i = issues[0]
        if i.value and i.target:
            return f"{i.value} / {i.target}"
        return i.value or i.message
    objects = {i.object_name for i in issues if i.object_name}
    if len(objects) > 1:
        return f"{len(issues)} issues on {len(objects)} objects"
    return f"{len(issues)} issues"


def problem_title(label: str) -> str:
    """How a check is named in results: its label without "Detect ".

    Check labels read as actions on buttons ("Detect N-gons"); results list the
    problem itself ("N-gons").
    """
    return label[len("Detect "):] if label.startswith("Detect ") else label


def plural(n: int, word: str) -> str:
    """'1 error', '2 errors'."""
    return f"{n} {word}" + ("" if n == 1 else "s")


def overall_status(results: List[CheckResult]) -> str:
    worst = PASS
    for r in results:
        if STATUS_ORDER.get(r.status, 3) < STATUS_ORDER[worst]:
            worst = r.status
    return worst
