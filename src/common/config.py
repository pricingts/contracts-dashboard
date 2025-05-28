from typing import Tuple, Dict

SHEETS: Dict[str, Tuple[str, str]] = {
    "all_quotes":        ("quotations_requested",   "All Quotes"),
    "contracts":         ("costs_sales_contracts",  "CONTRATOS"),
    "ground_quotations": ("quotations_requested",   "Ground Quotations"),
    "mejoras_q2":         ("contratos_id", "Mejoras Q2"),
    "tarifas_scrap_expo": ("contratos_id", "TARIFAS SCRAP EXPO"),
}