"""Thin wrapper around the Invezgo REST API (https://docs.invezgo.com/api/).

Only handles HTTP + auth + error translation. No Streamlit imports here so it
stays testable and reusable outside the UI layer.
"""
from __future__ import annotations

import requests

BASE_URL = "https://api.invezgo.com"


class InvezgoAPIError(Exception):
    def __init__(self, status_code: int, message: str):
        self.status_code = status_code
        self.message = message
        super().__init__(f"[{status_code}] {message}")


class InvezgoClient:
    def __init__(self, api_key: str, timeout: int = 20):
        if not api_key:
            raise ValueError("api_key is required")
        self.api_key = api_key
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(
            {
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            }
        )

    # -- low level -------------------------------------------------
    def _request(self, method: str, path: str, params: dict | None = None, json_body: dict | None = None):
        url = f"{BASE_URL}{path}"
        params = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            resp = self._session.request(method, url, params=params, json=json_body, timeout=self.timeout)
        except requests.RequestException as exc:
            raise InvezgoAPIError(0, f"Gagal menghubungi Invezgo API: {exc}") from exc

        if resp.status_code >= 400:
            message = resp.reason
            try:
                body = resp.json()
                message = body.get("message", message)
            except ValueError:
                pass
            if resp.status_code == 401:
                message = "API Key tidak valid / kadaluarsa. Cek kembali API Key Anda."
            elif resp.status_code == 402:
                message = "Paket langganan Invezgo Anda tidak mencukupi untuk endpoint ini."
            raise InvezgoAPIError(resp.status_code, message)

        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def get(self, path: str, **params):
        return self._request("GET", path, params=params)

    def post(self, path: str, json: dict | None = None):
        return self._request("POST", path, json_body=json)

    def delete(self, path: str, json: dict | None = None, **params):
        return self._request("DELETE", path, params=params, json_body=json)

    # -- reference data ----------------------------------------------
    def list_stock(self):
        return self.get("/analysis/list/stock")

    def list_broker(self):
        return self.get("/analysis/list/broker")

    def list_index(self):
        return self.get("/analysis/list/index")

    def notation(self):
        return self.get("/analysis/notation")

    def information(self, code: str):
        return self.get(f"/analysis/information/{code}")

    def search_stock(self, q: str):
        return self.get("/search/stock", q=q)

    # -- top movers / screening shortcuts -----------------------------
    def top_change(self, date: str, filter_column=None, filter_operator=None, filter_value=None):
        return self.get(
            "/analysis/top/change",
            date=date,
            filter_column=filter_column,
            filter_operator=filter_operator,
            filter_value=filter_value,
        )

    def top_foreign(self, date: str, filter_column=None, filter_operator=None, filter_value=None):
        return self.get(
            "/analysis/top/foreign",
            date=date,
            filter_column=filter_column,
            filter_operator=filter_operator,
            filter_value=filter_value,
        )

    def top_accumulation(self, date: str, filter_column=None, filter_operator=None, filter_value=None):
        return self.get(
            "/analysis/top/accumulation",
            date=date,
            filter_column=filter_column,
            filter_operator=filter_operator,
            filter_value=filter_value,
        )

    def top_ritel(self, date: str, filter_column=None, filter_operator=None, filter_value=None):
        return self.get(
            "/analysis/top/ritel",
            date=date,
            filter_column=filter_column,
            filter_operator=filter_operator,
            filter_value=filter_value,
        )

    # -- screener -----------------------------------------------------
    def screener_list(self):
        return self.get("/screener")

    def screener_run(self, formula: str, category: list[str] | None = None):
        payload = {"formula": formula}
        if category:
            payload["category"] = category
        return self.post("/screener/screen", json=payload)

    def screener_save(self, name: str, formula: str, description: str = None, scope=None, category=None):
        payload = {"name": name, "formula": formula}
        if description:
            payload["description"] = description
        if scope:
            payload["scope"] = scope
        if category:
            payload["category"] = category
        return self.post("/screener", json=payload)

    # -- charts ---------------------------------------------------------
    def chart_stock(self, code: str, frm: str, to: str):
        return self.get(f"/analysis/chart/stock/{code}", **{"from": frm, "to": to})

    def chart_multi_time(self, code: str, frm: str, to: str, timeframe: str):
        return self.get(f"/analysis/chart/multi-time/{code}", **{"from": frm, "to": to, "timeframe": timeframe})

    # -- fundamentals -----------------------------------------------------
    def keystat_chart(self, code: str, type_: str, name: str, limit: str = "1"):
        return self.get(f"/analysis/keystat-chart/{code}", type=type_, name=name, limit=limit)

    # -- broker / bandarmologi -------------------------------------------
    def summary_stock(self, code: str, frm: str, to: str, investor: str = "all", market: str = "RG"):
        return self.get(
            f"/analysis/summary/stock/{code}",
            **{"from": frm, "to": to, "investor": investor, "market": market},
        )

    def summary_chart_stock(self, code: str, frm: str, to: str, scope: str = "value", market: str = "RG"):
        return self.get(
            f"/analysis/summary-chart/stock/{code}",
            **{"from": frm, "to": to, "scope": scope, "market": market},
        )

    def inventory_chart_stock(
        self,
        code: str,
        frm: str,
        to: str,
        scope: str = "val",
        investor: str = "all",
        market: str = "ALL",
        limit: str | None = None,
    ):
        return self.get(
            f"/analysis/inventory-chart/stock/{code}",
            **{
                "from": frm,
                "to": to,
                "scope": scope,
                "investor": investor,
                "market": market,
                "limit": limit,
            },
        )

    def sankey_chart(self, code: str, date: str, type_: str = "value", buyer: str = "ALL", seller: str = "ALL", market: str = "RG"):
        return self.get(
            f"/analysis/sankey-chart/{code}",
            date=date,
            type=type_,
            buyer=buyer,
            seller=seller,
            market=market,
        )

    def stalker_list(self, code: str, frm: str, to: str, investor: str = "all", market: str = "RG"):
        return self.get(
            f"/analysis/stalker/list/{code}",
            **{"from": frm, "to": to, "investor": investor, "market": market},
        )

    def price_table(self, code: str, date: str):
        return self.get(f"/analysis/price-table/{code}", date=date)

    # -- watchlist ------------------------------------------------------
    def watchlist_groups(self):
        return self.get("/watchlists/group")

    def create_watchlist_group(self, name: str):
        return self.post("/watchlists/group", json={"name": name})

    def watchlist_items(self, group: str):
        return self.get("/watchlists", group=group)

    def add_watchlist_item(self, group: str, code: str, price: float, scope: list[str], note: str = None):
        payload = {"group": group, "code": code, "price": price, "scope": scope}
        if note:
            payload["note"] = note
        return self.post("/watchlists", json=payload)

    def delete_watchlist_items(self, ids: list[str]):
        return self.delete("/watchlists", json={"ids": ids})

    def update_watchlist_note(self, item_id: str, note: str):
        return self._request("PATCH", f"/watchlists/{item_id}", json_body={"note": note})

    # -- alerts -----------------------------------------------------------
    def alerts_list(self):
        return self.get("/alerts")

    def create_alert(self, name: str, formula: str, every: str, send: str, description: str = None, category=None, scope=None):
        payload = {"name": name, "formula": formula, "every": every, "send": send}
        if description:
            payload["description"] = description
        if category:
            payload["category"] = category
        if scope:
            payload["scope"] = scope
        return self.post("/alerts", json=payload)

    def test_alert(self, formula: str, category: list[str] | None = None):
        payload = {"formula": formula}
        if category:
            payload["category"] = category
        return self.post("/alerts/test", json=payload)

    def delete_alert(self, alert_id: str):
        return self._request("DELETE", f"/alerts/{alert_id}")
