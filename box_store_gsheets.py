"""
Google Sheets ULD / 箱型資料存取 adapter — v1.13.4.

修正重點：
1. Google Sheet 若缺少 allow_center_load，讀取時自動建立欄位。
2. 儲存 ULD 時寫入完整 canonical schema。
3. 每次 update 後主動清除 Streamlit data cache。
4. 回讀驗證加入短暫 retry，避免 Google Sheets 更新完成但本次 read
   仍拿到舊快取，造成「其實已寫入、卻顯示同步失敗」。
"""

from __future__ import annotations

import time
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

OPTIONAL_SCHEMA_DEFAULTS = {
    "allow_center_load": False,
    "center_positions": 2,
    "enabled": True,
    "notes": "",
}


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

    def _clear_read_cache(self) -> None:
        """
        st-gsheets-connection 的 read() 使用 Streamlit cache_data。
        官方 update 範例在寫入後也會 clear cache 再 rerun。
        """
        try:
            st.cache_data.clear()
        except Exception:
            pass

    def _read_dataframe(self) -> pd.DataFrame:
        df = self.conn.read(
            spreadsheet=self.spreadsheet,
            worksheet=self.worksheet,
            ttl=0,
        )
        return pd.DataFrame() if df is None else df.copy()

    def _ensure_optional_schema(self, df: pd.DataFrame) -> pd.DataFrame:
        if df.empty and not list(df.columns):
            return df

        changed = False

        for column, default in OPTIONAL_SCHEMA_DEFAULTS.items():
            if column not in df.columns:
                df[column] = default
                changed = True

        if changed:
            self.conn.update(
                spreadsheet=self.spreadsheet,
                worksheet=self.worksheet,
                data=df,
            )
            self._clear_read_cache()

        return df

    def load_boxes(self) -> list[dict[str, Any]]:
        df = self._read_dataframe()

        if df.empty:
            return []

        df = self._ensure_optional_schema(df)
        records = []

        for raw in df.to_dict("records"):
            clean = {
                key: (None if pd.isna(value) else value)
                for key, value in raw.items()
            }
            records.append(normalize_box(clean))

        return records

    def _normalized_rows_by_id(
        self,
        df: pd.DataFrame,
    ) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}

        if df is None or df.empty:
            return result

        for raw in df.to_dict("records"):
            clean = {
                key: (None if pd.isna(value) else value)
                for key, value in raw.items()
            }
            normalized = normalize_box(clean)
            result[str(normalized["box_id"]).strip()] = normalized

        return result

    def _verify_saved_records(
        self,
        verify: pd.DataFrame,
        expected_records: list[dict[str, Any]],
    ) -> tuple[bool, str]:
        missing_columns = [
            col
            for col in CANONICAL_COLUMNS
            if col not in verify.columns
        ]

        if missing_columns:
            return (
                False,
                "Google Sheets 缺少欄位："
                + ", ".join(missing_columns),
            )

        expected_by_id = {
            str(r["box_id"]).strip(): r
            for r in expected_records
        }
        actual_by_id = self._normalized_rows_by_id(verify)

        for box_id, expected in expected_by_id.items():
            if box_id not in actual_by_id:
                return False, f"找不到 ULD {box_id}"

            actual = actual_by_id[box_id]

            if bool(actual.get("allow_center_load", False)) != bool(
                expected.get("allow_center_load", False)
            ):
                return (
                    False,
                    f"{box_id} 的 allow_center_load 尚未反映最新值",
                )

            if int(actual.get("center_positions", 2) or 2) != int(
                expected.get("center_positions", 2) or 2
            ):
                return (
                    False,
                    f"{box_id} 的 center_positions 尚未反映最新值",
                )

            if bool(actual.get("enabled", True)) != bool(
                expected.get("enabled", True)
            ):
                return (
                    False,
                    f"{box_id} 的 enabled 尚未反映最新值",
                )

        return True, ""

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
            item["allow_center_load"] = bool(
                item.get("allow_center_load", False)
            )
            item["center_positions"] = int(
                item.get("center_positions", 2) or 2
            )
            item["enabled"] = bool(
                item.get("enabled", True)
            )

            records.append(item)

        df = pd.DataFrame(
            records,
            columns=CANONICAL_COLUMNS,
        )

        # update() 本身若 Google API 寫入失敗會直接 raise。
        updated = self.conn.update(
            spreadsheet=self.spreadsheet,
            worksheet=self.worksheet,
            data=df,
        )

        if updated is None:
            raise RuntimeError(
                "Google Sheets update() 未回傳資料，請確認 Service Account 寫入權限。"
            )

        # 重要：清掉 read() 舊快取。
        self._clear_read_cache()

        # Google API / cache 可能在非常短的時間內仍讀到舊值。
        # 最多重試 4 次，總等待約 2.4 秒。
        delays = (0.0, 0.4, 0.8, 1.2)
        last_reason = ""

        for delay in delays:
            if delay:
                time.sleep(delay)

            self._clear_read_cache()
            verify = self._read_dataframe()

            ok, reason = self._verify_saved_records(
                verify,
                records,
            )

            if ok:
                return

            last_reason = reason

        raise RuntimeError(
            "Google Sheets 寫入後回讀驗證仍未取得最新資料："
            + last_reason
            + "。請重新整理一次頁面；若 Google Sheet 已更新，"
              "代表先前是讀取快取延遲。"
        )

    def connection_info(self) -> dict[str, str]:
        return {
            "backend": "Google Sheets",
            "spreadsheet": self.spreadsheet,
            "worksheet": self.worksheet,
        }

    def healthcheck(self) -> tuple[bool, str]:
        try:
            self._clear_read_cache()
            df = self._read_dataframe()
            columns = list(df.columns)

            allow_center_status = (
                "已存在"
                if "allow_center_load" in columns
                else "尚未建立（開啟 ULD 管理頁會自動建立）"
            )

            return (
                True,
                "Google Sheets 連線正常"
                f"｜worksheet={self.worksheet}"
                f"｜目前 {len(df.index)} 筆 ULD"
                f"｜allow_center_load：{allow_center_status}",
            )
        except Exception as exc:
            return False, f"Google Sheets 連線失敗：{exc}"
