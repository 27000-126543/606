__all__ = [
    "User",
    "Team",
    "UserTeam",
    "RawLog",
    "ProcessedLog",
    "Anomaly",
    "BaselineConfig",
    "WorkOrder",
    "FollowUpTask",
    "Playbook",
    "PlaybookExecution",
    "ServiceNode",
    "ServiceDependency",
    "ChangeRecord",
    "AuditLog",
    "CaseLibrary",
    "DailyReport",
    "MetricBaseline",
    "BaselineHistory",
]


def __getattr__(name):
    import importlib
    if name in ["User", "Team", "UserTeam"]:
        mod = importlib.import_module(".user", package=__name__)
        return getattr(mod, name)
    if name in ["RawLog", "ProcessedLog"]:
        mod = importlib.import_module(".log", package=__name__)
        return getattr(mod, name)
    if name in ["Anomaly", "BaselineConfig"]:
        mod = importlib.import_module(".anomaly", package=__name__)
        return getattr(mod, name)
    if name in ["WorkOrder", "FollowUpTask"]:
        mod = importlib.import_module(".ticket", package=__name__)
        return getattr(mod, name)
    if name in ["Playbook", "PlaybookExecution"]:
        mod = importlib.import_module(".playbook", package=__name__)
        return getattr(mod, name)
    if name in ["ServiceNode", "ServiceDependency", "ChangeRecord"]:
        mod = importlib.import_module(".topology", package=__name__)
        return getattr(mod, name)
    if name == "AuditLog":
        mod = importlib.import_module(".audit", package=__name__)
        return getattr(mod, name)
    if name in ["CaseLibrary", "DailyReport"]:
        mod = importlib.import_module(".report", package=__name__)
        return getattr(mod, name)
    if name in ["MetricBaseline", "BaselineHistory"]:
        mod = importlib.import_module(".baseline", package=__name__)
        return getattr(mod, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
