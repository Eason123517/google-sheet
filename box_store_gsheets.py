"""
Google Sheets ULD / 箱型資料存取 adapter — v1.13.2 online.

預設連接原專案 Google Sheet：
https://docs.google.com/spreadsheets/d/1KJntRmxBOLyl1lfEo1Sqi8MS59GNXo12z-ETlkfEX-8/edit?usp=sharing

worksheet:
boxes

正式部署建議：
- Streamlit Community Cloud / 其他 Streamlit hosting
- Google Cloud Service Account
- Sheet 分享給 Service Account client_email，權限「編輯者」

注意：
app.py / packing engine 不直接操作 Google Sheets。
資料來源透過 box_store.py facade 存取。
"""

from __future__ import annotations

from typing import Any

import pandas as pd
import streamlit as st
from streamlit_gsheets import GSheetsConnection

from box_store import CANONICAL_COLUMNS, normalize_box


DEFAULT_SPREADSHEET = (
    "https://docs.google.com/spreadsheets/d/"
    "1KJntRmxBOLyl1lfEo1Sqi8MS59GNXo12z-ETlkfEX-8/"
    "edit?usp=sharing"
)
DEFAULT_WORKSHEET = "boxes"


class GoogleSheetsBoxStore:
    def __init__(self):
        try:
            config = st.secrets.get("box_store", {})
        except Exception:
            config = {}

        self.spreadsheet = str(
            config.get("spreadsheet", DEFAULT_SPREADSHEET)
        ).strip() or DEFAULT_SPREADSHEET

        self.worksheet = str(
            config.get("worksheet", DEFAULT_WORKSHEET)
        ).strip() or DEFAULT_WORKSHEET

        self.conn = st.connection(
            "gsheets",
            type=GSheetsConnection,
        )

    def load_boxes(self) -> list[dict[str, Any]]:
        df = self.conn.read(
            spreadsheet=self.spreadsheet,
            worksheet=self.worksheet,
            ttl=0,
        )

        if df is None or df.empty:
            return []

        records = []

        for raw in df.to_dict("records"):
            clean = {
                key: (None if pd.isna(value) else value)
                for key, value in raw.items()
            }
            records.append(normalize_box(clean))

        return records

    def save_boxes(self, boxes: list[dict[str, Any]]) -> None:
        records = []

        for raw in boxes:
            item = normalize_box(raw).copy()

            item["compatible_aircraft"] = ",".join(
                item.get("compatible_aircraft", [])
            )
            item["compatible_zones"] = ",".join(
                item.get("compatible_zones", [])
            )

            records.append(item)

        df = pd.DataFrame(
            records,
            columns=CANONICAL_COLUMNS,
        )

        self.conn.update(
            spreadsheet=self.spreadsheet,
            worksheet=self.worksheet,
            data=df,
        )

    def connection_info(self) -> dict[str, str]:
        return {
            "backend": "Google Sheets",
            "spreadsheet": self.spreadsheet,
            "worksheet": self.worksheet,
        }

    def healthcheck(self) -> tuple[bool, str]:
        try:
            df = self.conn.read(
                spreadsheet=self.spreadsheet,
                worksheet=self.worksheet,
                ttl=0,
            )
            rows = 0 if df is None else len(df.index)
            return (
                True,
                f"Google Sheets 連線正常｜worksheet={self.worksheet}｜目前 {rows} 筆 ULD",
            )
        except Exception as exc:
            return False, f"Google Sheets 連線失敗：{exc}"
