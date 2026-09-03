"""Lazy proxy for pandas. These scripts are imported (not just run standalone)
by wrapper/backend/app/pipeline/apollo_enrich.py, which deploys as a Vercel
Python serverless function - importing pandas eagerly here meant every cold
start paid pandas's import cost even for requests that never touch a
DataFrame. Deferring the import to first use fixes that without changing
behavior when these scripts are run directly.
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
