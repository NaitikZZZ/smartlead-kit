"""Lazy proxies for heavy third-party imports (pandas, anthropic).

This app deploys to Vercel as a single Python serverless function, and every
pipeline submodule gets imported at cold start regardless of which route is
hit - so importing pandas/anthropic eagerly at module load time meant even a
static endpoint like /api/health or /api/runs/icp-options paid their import
cost (pandas alone is several hundred ms) on every cold start. These proxies
defer the real import to first use, so only requests that actually touch a
DataFrame or the Anthropic client pay for it.
"""
import importlib


class _LazyModule:
    def __init__(self, name):
        self.__dict__["_name"] = name
        self.__dict__["_mod"] = None

    def _load(self):
        mod = self.__dict__["_mod"]
        if mod is None:
            mod = importlib.import_module(self.__dict__["_name"])
            self.__dict__["_mod"] = mod
        return mod

    def __getattr__(self, attr):
        return getattr(self._load(), attr)


pd = _LazyModule("pandas")


class _LazyAnthropic:
    """Stands in for `from anthropic import Anthropic` - callable just like
    the real class, imports the SDK on first instantiation."""

    def __call__(self, *args, **kwargs):
        from anthropic import Anthropic as _Anthropic
        return _Anthropic(*args, **kwargs)


Anthropic = _LazyAnthropic()
