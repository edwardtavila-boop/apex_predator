"""
APEX PREDATOR  //  data
=======================
Market data ingestion, cache catalog, cleaning, slippage, on-chain + social.
"""

from apex_predator.data.bybit_ws import BybitWSCapture
from apex_predator.data.cleaning import (
    detect_duplicates,
    detect_gaps,
    fill_gaps,
    remove_outliers_mad,
    validate_bar,
)
from apex_predator.data.databento_client import DataBentoClient
from apex_predator.data.models import (
    DataIntegrityReport,
    DatasetManifest,
    DatasetRef,
    DataSource,
)
from apex_predator.data.onchain_blockscout import BlockscoutClient
from apex_predator.data.parquet_loader import ParquetLoader
from apex_predator.data.sentiment_lunarcrush import LunarCrushClient
from apex_predator.data.slippage_model import SlippageModel

__all__ = [
    "BlockscoutClient",
    "BybitWSCapture",
    "DataBentoClient",
    "DataIntegrityReport",
    "DataSource",
    "DatasetManifest",
    "DatasetRef",
    "LunarCrushClient",
    "ParquetLoader",
    "SlippageModel",
    "detect_duplicates",
    "detect_gaps",
    "fill_gaps",
    "remove_outliers_mad",
    "validate_bar",
]
