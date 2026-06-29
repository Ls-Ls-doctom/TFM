from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

from _common import (
    BRONZE_DIR,
    REPORTS_DIR,
    SILVER_DIR,
    TARGET_CITIES,
    clean_columns,
    ensure_dirs,
    infer_city_from_path,
    municipality_code,
    now,
    normalize_column,
    read_csv_flexible,
    read_sepe_csv,
    relative,
    to_month_date,
    to_number,
    to_year_date,
    write_csv,
    write_json,
)


PRIORITY_MUNICIPAL_KEYWORDS = [
    "renda",
    "renta",
    "income",
    "poblacion",
    "demografic",
    "demograf",
    "trafic",
    "transit",
    "bizi",
    "bicic",
    "sostenibilidad",
    "acciden",
]


def main() -> int:
    ensure_dirs()
    if not BRONZE_DIR.exists():
        raise FileNotFoundError(f"No existe Bronze: {BRONZE_DIR}. Ejecuta primero las APIs.")

    report: list[dict[str, Any]] = []
    outputs: dict[str, pd.DataFrame] = {}

    outputs.update(clean_ine(report))
    outputs.update(clean_sepe(report))
    outputs.update(clean_mitma(report))
    outputs.update(clean_municipal_priority(report))

    for key, df in outputs.items():
        write_csv(df, SILVER_DIR / key)

    summary = {
        "generated_at": now(),
        "silver_dir": relative(SILVER_DIR),
        "tables_total": len(outputs),
        "rows_by_table": {key: int(len(df)) for key, df in outputs.items()},
        "resources": report,
    }
    write_json(REPORTS_DIR / "cleaning_silver.json", summary)

    print(f"Silver generado en: {SILVER_DIR}")
    for key, df in outputs.items():
        print(f"{key}: {len(df)} filas")
    return 0


def clean_ine(report: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    outputs: dict[str, pd.DataFrame] = {}
    ine_dir = BRONZE_DIR / "apis" / "ine"
    population_path = ine_dir / "poblacion_municipio_sexo" / "poblacion_municipio_sexo_csv_semicolon.csv"
    birthplace_path = ine_dir / "poblacion_municipio_pais_nacimiento" / "poblacion_municipio_pais_nacimiento_csv_semicolon.csv"

    if population_path.exists():
        df = clean_columns(read_csv_flexible(population_path))
        df["municipality_code"] = df["municipios"].map(municipality_code)
        df = df[(df["municipality_code"].isin(TARGET_CITIES)) & (df["sexo"].astype(str).str.lower() == "total")].copy()
        df["city"] = df["municipality_code"].map(TARGET_CITIES)
        df["date"] = df["periodo"].map(to_year_date)
        df["population_total"] = df["total"].map(to_number)
        out = df[["city", "municipality_code", "date", "population_total", "total_nacional", "municipios"]].dropna(
            subset=["population_total"]
        )
        outputs["ine/poblacion_municipal.csv"] = out
        report.append(item(population_path, "OK", len(out), "INE poblacion municipal filtrada a ciudades objetivo"))

    if birthplace_path.exists():
        df = clean_columns(read_csv_flexible(birthplace_path))
        df["municipality_code"] = df["municipios"].map(municipality_code)
        if "pais_de_nacimiento" not in df.columns:
            country_col = next((col for col in df.columns if "nacimiento" in col), "")
        else:
            country_col = "pais_de_nacimiento"
        df = df[
            (df["municipality_code"].isin(TARGET_CITIES))
            & (df["sexo"].astype(str).str.lower() == "total")
            & (df[country_col].astype(str).str.lower() == "total")
        ].copy()
        df["city"] = df["municipality_code"].map(TARGET_CITIES)
        df["date"] = df["periodo"].map(to_year_date)
        df["population_birthplace_total"] = df["total"].map(to_number)
        out = df[["city", "municipality_code", "date", "population_birthplace_total", "provincias", "municipios"]].dropna(
            subset=["population_birthplace_total"]
        )
        outputs["ine/poblacion_pais_nacimiento_total.csv"] = out
        report.append(item(birthplace_path, "OK", len(out), "INE poblacion por pais nacimiento filtrada"))

    outputs.update(clean_ine_urban_indicators(ine_dir, report))
    outputs.update(clean_ine_cpi(ine_dir, report))
    outputs.update(clean_ine_rent_index(ine_dir, report))
    outputs.update(clean_ine_business_units(ine_dir, report))

    return outputs


URBAN_TABLES = {
    "indicadores_urbanos_demografia": "demography",
    "indicadores_urbanos_social": "living_conditions",
    "indicadores_urbanos_economia": "economy",
    "indicadores_urbanos_educacion": "education",
    "indicadores_urbanos_suelo": "environment",
    "indicadores_urbanos_movilidad": "mobility",
    "indicadores_urbanos_turismo": "tourism",
}

URBAN_CITY_ALIASES = {
    "barcelona": "Barcelona",
    "madrid": "Madrid",
    "valencia": "Valencia",
    "val_ncia": "Valencia",
    "sevilla": "Sevilla",
    "bilbao": "Bilbao",
    "malaga": "Malaga",
    "m_laga": "Malaga",
    "zaragoza": "Zaragoza",
}

URBAN_INDICATOR_SPECS = [
    ("poblacion_residente", "population_resident", "persons", "demography"),
    ("poblacion_de_0_14", "population_0_14_pct", "percent", "demography"),
    ("poblacion_de_15_64", "population_15_64_pct", "percent", "demography"),
    ("poblacion_65", "population_65_plus_pct", "percent", "demography"),
    ("edad_mediana", "median_age", "years", "demography"),
    ("nativos_nacionales", "native_born_pct", "percent", "demography"),
    ("nacidos_en_el_extranjero", "foreign_born_pct", "percent", "demography"),
    ("extranjeros_sobre", "foreign_population_pct", "percent", "demography"),
    ("nacionales_sobre", "national_population_pct", "percent", "demography"),
    ("natalidad", "birth_rate", "per_thousand", "demography"),
    ("mortalidad", "mortality_rate", "per_thousand", "demography"),
    ("esperanza_de_vida", "life_expectancy", "years", "demography"),
    ("hijos_por_mujer", "fertility_rate", "children_per_woman", "demography"),
    ("hogares_de_una_persona", "single_person_households_pct", "percent", "living_conditions"),
    ("total_de_hogares", "households_total", "households", "living_conditions"),
    ("tamano_medio_de_los_hogares", "household_size", "persons", "living_conditions"),
    ("viviendas_convencionales_segun_catastro", "dwellings_cadastre", "dwellings", "housing"),
    ("viviendas_convencionales_segun_censo", "dwellings_census", "dwellings", "housing"),
    ("viviendas_vac", "vacant_dwellings_pct", "percent", "housing"),
    ("mediana_del_alquiler_anual", "rent_median_eur_m2_year", "eur_m2_year", "housing"),
    ("mediana_del_alquiler_mensual", "rent_median_monthly", "eur_month", "housing"),
    ("primer_cuartil_del_alquiler_anual", "rent_q1_eur_m2_year", "eur_m2_year", "housing"),
    ("primer_cuartil_del_alquiler_mensual", "rent_q1_monthly", "eur_month", "housing"),
    ("tercer_cuartil_del_alquiler_anual", "rent_q3_eur_m2_year", "eur_m2_year", "housing"),
    ("tercer_cuartil_del_alquiler_mensual", "rent_q3_monthly", "eur_month", "housing"),
    ("alquiler_anual_medio", "rent_mean_eur_m2_year", "eur_m2_year", "housing"),
    ("alquiler_mensual_medio", "rent_mean_monthly", "eur_month", "housing"),
    ("precio_medio_por_metro_cuadrado_de_la_vivienda_tipo_unifamiliar", "house_price_mean_m2_detached", "eur_m2", "housing"),
    ("precio_medio_por_metro_cuadrado_de_la_vivienda_tipo_piso", "house_price_mean_m2_flat", "eur_m2", "housing"),
    ("precio_medio_por_metro_cuadrado_de_la_vivienda", "house_price_mean_m2", "eur_m2", "housing"),
    ("precio_medio_de_la_vivienda_tipo_unifamiliar", "house_price_mean_detached", "eur", "housing"),
    ("precio_medio_de_la_vivienda_tipo_piso", "house_price_mean_flat", "eur", "housing"),
    ("precio_medio_de_la_vivienda", "house_price_mean", "eur", "housing"),
    ("robos_y_hurtos", "robbery_theft_rate", "per_thousand", "safety"),
    ("libertad_sexual", "sexual_offences_rate", "per_thousand", "safety"),
    ("infracciones_penales", "crime_rate", "per_thousand", "safety"),
    ("tasa_de_desempleo", "unemployment_rate", "percent", "employment"),
    ("ocupados_entre_20_64", "employment_rate_20_64", "percent", "employment"),
    ("tasa_de_actividad", "activity_rate", "percent", "employment"),
    ("empleo_en_servicios", "services_employment_share", "percent", "economy"),
    ("empleo_en_industria", "industry_employment_share", "percent", "economy"),
    ("renta_neta_media_anual_de_los_hogares", "net_income_household", "eur", "economy"),
    ("renta_neta_media_anual_por_habitante", "net_income_per_capita", "eur", "economy"),
    ("renta_neta_media_anual_por_unidad_de_consumo", "net_income_consumption_unit", "eur", "economy"),
    ("guarder", "childcare_coverage_pct", "percent", "education"),
    ("isced_0_1_o_2", "education_low_pct", "percent", "education"),
    ("isced_3_o_4", "education_mid_pct", "percent", "education"),
    ("isced_5_6_7_o_8", "education_high_pct", "percent", "education"),
    ("superficie_total", "area_total_km2", "km2", "environment"),
    ("tejido_urbano_residencial_discontinuo", "land_discontinuous_urban_pct", "percent", "environment"),
    ("tejido_urbano_residencial_continuo", "land_continuous_urban_pct", "percent", "environment"),
    ("unidades_industriales", "land_industrial_commercial_pct", "percent", "environment"),
    ("infraestructuras_de_transporte", "land_transport_infrastructure_pct", "percent", "environment"),
    ("otras_zonas_artificiales", "land_other_artificial_pct", "percent", "environment"),
    ("zonas_verdes_urbanas", "land_urban_green_pct", "percent", "environment"),
    ("zonas_agr", "land_agricultural_pct", "percent", "environment"),
    ("zonas_naturales", "land_natural_pct", "percent", "environment"),
    ("relacion_de_zona_verdes", "green_space_to_residential_ratio", "ratio", "environment"),
    ("desplazamientos_al_trabajo_en_coche", "commute_car_pct", "percent", "mobility"),
    ("desplazamientos_al_trabajo_a_pie", "commute_walk_pct", "percent", "mobility"),
    ("desplazamientos_al_trabajo_en_transporte_publico", "commute_public_transport_pct", "percent", "mobility"),
    ("duracion_media_del_desplazamiento", "commute_duration_minutes", "minutes", "mobility"),
    ("pernoctaciones_tur", "tourism_overnight_stays", "overnight_stays", "tourism"),
    ("plazas_disponibles", "tourism_beds", "beds", "tourism"),
]


def clean_ine_urban_indicators(ine_dir: Path, report: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    frames: list[pd.DataFrame] = []
    for dataset, default_category in URBAN_TABLES.items():
        path = ine_dir / dataset / f"{dataset}_csv_semicolon.csv"
        if not path.exists():
            continue
        df = clean_columns(read_csv_flexible(path))
        required = {"municipios", "indicadores", "periodo", "total"}
        if not required.issubset(df.columns):
            report.append(item(path, "SKIPPED_SCHEMA", 0, f"Faltan columnas: {sorted(required - set(df.columns))}"))
            continue
        df["city"] = df["municipios"].map(city_from_urban_name)
        df = df[df["city"].notna()].copy()
        if "sexo" in df.columns:
            df = df[df["sexo"].astype(str).map(normalize_column) == "total"].copy()
        specs = df["indicadores"].map(urban_indicator_spec)
        df["variable"] = specs.map(lambda spec: spec[0] if spec else None)
        df["unit"] = specs.map(lambda spec: spec[1] if spec else None)
        df["category"] = specs.map(lambda spec: spec[2] if spec else default_category)
        df["date"] = df["periodo"].map(to_year_date)
        df["value"] = df["total"].map(to_number)
        df["source"] = "INE Indicadores Urbanos"
        df["quality_score"] = 9
        df["territorial_scope"] = "city"
        df["source_geography"] = df["municipios"]
        df["notes"] = "Serie anual comparable de Indicadores Urbanos del INE."
        keep = [
            "city", "date", "variable", "value", "source", "quality_score", "category", "unit",
            "territorial_scope", "source_geography", "indicadores", "notes",
        ]
        out = df[keep].dropna(subset=["variable", "value", "date"]).drop_duplicates()
        frames.append(out)
        report.append(item(path, "OK", len(out), f"INE {dataset} filtrado a ciudades objetivo"))
    if not frames:
        return {}
    return {"ine/indicadores_urbanos.csv": pd.concat(frames, ignore_index=True).drop_duplicates()}


def clean_ine_cpi(ine_dir: Path, report: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    path = ine_dir / "ipc_provincial_anual" / "ipc_provincial_anual_csv_semicolon.csv"
    if not path.exists():
        return {}
    df = clean_columns(read_csv_flexible(path))
    province_col = next((col for col in df.columns if col.endswith("provincias")), "")
    required = {province_col, "grupos_ecoicop_ver_2", "tipo_de_dato", "periodo", "total"}
    if not province_col or not required.issubset(df.columns):
        report.append(item(path, "SKIPPED_SCHEMA", 0, "Esquema IPC provincial no reconocido"))
        return {}
    province_cities = {"08": "Barcelona", "28": "Madrid", "46": "Valencia", "41": "Sevilla", "48": "Bilbao", "29": "Malaga", "50": "Zaragoza"}
    df["province_code"] = df[province_col].astype(str).str.extract(r"(\d{2})", expand=False)
    df["city"] = df["province_code"].map(province_cities)
    df = df[df["city"].notna()].copy()
    specs = df.apply(cpi_indicator_spec, axis=1)
    df["variable"] = specs.map(lambda spec: spec[0] if spec else None)
    df["unit"] = specs.map(lambda spec: spec[1] if spec else None)
    df["date"] = df["periodo"].map(to_year_date)
    df["value"] = df["total"].map(to_number)
    df["source"] = "INE IPC provincial (proxy urbano)"
    df["quality_score"] = 7
    df["category"] = "cost_of_living"
    df["territorial_scope"] = "province_proxy"
    df["source_geography"] = df[province_col]
    df["notes"] = "El IPC no se publica a escala municipal; se asigna a la ciudad el dato de su provincia."
    keep = ["city", "date", "variable", "value", "source", "quality_score", "category", "unit", "territorial_scope", "source_geography", "notes"]
    out = df[keep].dropna(subset=["variable", "value", "date"]).drop_duplicates()
    report.append(item(path, "OK", len(out), "IPC anual provincial filtrado y etiquetado como proxy"))
    return {"ine/ipc_provincial_anual.csv": out}


def clean_ine_rent_index(ine_dir: Path, report: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    path = ine_dir / "ipva_municipal" / "ipva_municipal_csv_semicolon.csv"
    if not path.exists():
        return {}
    df = clean_columns(read_csv_flexible(path))
    municipality_col = next((col for col in df.columns if col.endswith("municipio")), "")
    required = {municipality_col, "tipo_de_dato", "periodo", "total"}
    if not municipality_col or not required.issubset(df.columns):
        report.append(item(path, "SKIPPED_SCHEMA", 0, "Esquema IPVA municipal no reconocido"))
        return {}
    df["municipality_code"] = df[municipality_col].map(municipality_code)
    df["city"] = df["municipality_code"].map(TARGET_CITIES)
    df = df[df["city"].notna()].copy()
    kind = df["tipo_de_dato"].astype(str).map(normalize_column)
    df["variable"] = kind.map(lambda value: "rent_price_change_pct" if "variacion" in value else "rent_price_index")
    df["unit"] = kind.map(lambda value: "percent" if "variacion" in value else "index_2015")
    df["date"] = df["periodo"].map(to_year_date)
    df["value"] = df["total"].map(to_number)
    df["source"] = "INE IPVA"
    df["quality_score"] = 9
    df["category"] = "housing"
    df["territorial_scope"] = "city"
    df["source_geography"] = df[municipality_col]
    df["notes"] = "IPVA municipal. No cubre territorios forales; Bilbao puede no disponer de observaciones."
    keep = ["city", "date", "variable", "value", "source", "quality_score", "category", "unit", "territorial_scope", "source_geography", "notes"]
    out = df[keep].dropna(subset=["value", "date"]).drop_duplicates()
    report.append(item(path, "OK", len(out), "IPVA municipal filtrado a ciudades objetivo"))
    return {"ine/ipva_municipal.csv": out}


def clean_ine_business_units(ine_dir: Path, report: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    path = ine_dir / "dirce_locales_provinciales" / "dirce_locales_provinciales_csv_semicolon.csv"
    if not path.exists():
        return {}
    df = clean_columns(read_csv_flexible(path))
    province_col = next((col for col in df.columns if col.endswith("provincias")), "")
    required = {province_col, "estrato_de_asalariados", "periodo", "total"}
    if not province_col or not required.issubset(df.columns):
        report.append(item(path, "SKIPPED_SCHEMA", 0, "Esquema DIRCE provincial no reconocido"))
        return {}
    province_cities = {"08": "Barcelona", "28": "Madrid", "46": "Valencia", "41": "Sevilla", "48": "Bilbao", "29": "Malaga", "50": "Zaragoza"}
    df["province_code"] = df[province_col].astype(str).str.extract(r"(\d{2})", expand=False)
    df["city"] = df["province_code"].map(province_cities)
    strata = df["estrato_de_asalariados"].astype(str).map(normalize_column)
    df = df[df["city"].notna() & strata.isin({"total", "sin_asalariados"})].copy()
    strata = df["estrato_de_asalariados"].astype(str).map(normalize_column)
    df["variable"] = strata.map(lambda value: "business_local_units" if value == "total" else "business_local_units_no_employees")
    df["date"] = df["periodo"].map(to_year_date)
    df["value"] = df["total"].map(to_number)
    df["source"] = "INE DIRCE provincial (proxy urbano)"
    df["quality_score"] = 7
    df["category"] = "business"
    df["unit"] = "local_units"
    df["territorial_scope"] = "province_proxy"
    df["source_geography"] = df[province_col]
    df["notes"] = "DIRCE se publica a escala provincial; no representa exclusivamente la ciudad. Hay ruptura metodologica desde 2023."
    keep = ["city", "date", "variable", "value", "source", "quality_score", "category", "unit", "territorial_scope", "source_geography", "notes"]
    out = df[keep].dropna(subset=["value", "date"]).drop_duplicates()
    report.append(item(path, "OK", len(out), "DIRCE provincial filtrado y etiquetado como proxy"))
    return {"ine/dirce_locales_provinciales.csv": out}


def city_from_urban_name(value: object) -> str | None:
    normalized = normalize_column(value)
    return URBAN_CITY_ALIASES.get(normalized)


def urban_indicator_spec(value: object) -> tuple[str, str, str] | None:
    normalized = normalize_column(value)
    for fragment, variable, unit, category in URBAN_INDICATOR_SPECS:
        if fragment in normalized:
            return variable, unit, category
    return None


def cpi_indicator_spec(row: pd.Series) -> tuple[str, str] | None:
    group = normalize_column(row.get("grupos_ecoicop_ver_2", ""))
    kind = normalize_column(row.get("tipo_de_dato", ""))
    groups = [
        ("ndice_general", "cpi_general"),
        ("alimentos_y_bebidas_no_alcoholicas", "cpi_food"),
        ("vivienda_agua_electricidad_gas", "cpi_housing_energy"),
        ("transporte", "cpi_transport"),
        ("restaurantes_y_servicios_de_alojamiento", "cpi_hospitality"),
    ]
    prefix = next((variable for fragment, variable in groups if fragment in group), None)
    if not prefix:
        return None
    if "variacion" in kind:
        return f"{prefix}_change_pct", "percent"
    if "media_anual" in kind:
        return f"{prefix}_index", "index_2025"
    return None


def clean_sepe(report: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    outputs: dict[str, pd.DataFrame] = {}
    configs = {
        "paro_registrado": ("total_paro_registrado", "unemployed_registered"),
        "contratos_registrados": ("total_contratos", "contracts_registered"),
        "demandantes_empleo": ("total_dtes_empleo", "job_seekers"),
    }
    for folder, (total_col, variable) in configs.items():
        frames = []
        for path in sorted((BRONZE_DIR / "apis" / "sepe" / folder / "resources").glob("*.csv")):
            df = read_sepe_csv(path)
            if df.empty:
                report.append(item(path, "EMPTY", 0, f"SEPE {folder} sin filas"))
                continue
            code_col = next((col for col in df.columns if "codigo_municipio" in col), "")
            if not code_col or total_col not in df.columns:
                report.append(item(path, "SKIPPED_SCHEMA", 0, f"Columnas no compatibles para {folder}"))
                continue
            df["municipality_code"] = df[code_col].map(municipality_code)
            df = df[df["municipality_code"].isin(TARGET_CITIES)].copy()
            df["city"] = df["municipality_code"].map(TARGET_CITIES)
            df["date"] = df["codigo_mes"].map(to_month_date)
            df["value"] = df[total_col].map(to_number)
            df["variable"] = variable
            keep = ["city", "municipality_code", "date", "variable", "value", "municipio", "provincia", "comunidad_autonoma"]
            frames.append(df[[col for col in keep if col in df.columns]].dropna(subset=["value"]))
            report.append(item(path, "OK", int(len(df)), f"SEPE {folder} filtrado a ciudades objetivo"))
        if frames:
            outputs[f"sepe/{folder}.csv"] = pd.concat(frames, ignore_index=True).drop_duplicates()
    return outputs


def clean_mitma(report: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    outputs: dict[str, pd.DataFrame] = {}
    path = BRONZE_DIR / "apis" / "mitma" / "relaciones_distrito_mitma.csv"
    if not path.exists():
        return outputs
    df = clean_columns(read_csv_flexible(path))
    out = df.copy()
    outputs["mitma/relaciones_distrito_mitma.csv"] = out
    report.append(item(path, "OK", len(out), "MITMA relacion distrito normalizada"))
    return outputs


def clean_municipal_priority(report: list[dict[str, Any]]) -> dict[str, pd.DataFrame]:
    outputs: dict[str, pd.DataFrame] = {}
    rows = []
    for path in sorted((BRONZE_DIR / "municipios").rglob("*.csv")):
        text = str(path).lower()
        if not any(keyword in text for keyword in PRIORITY_MUNICIPAL_KEYWORDS):
            continue
        city = infer_city_from_path(path)
        if not city:
            continue
        try:
            df = clean_columns(read_csv_flexible(path))
        except Exception as exc:  # noqa: BLE001
            report.append(item(path, "ERROR", 0, str(exc)))
            continue
        df = df.dropna(how="all").drop_duplicates()
        if df.empty:
            report.append(item(path, "EMPTY", 0, "Municipal prioritario sin filas"))
            continue
        df["city"] = city
        df["source_file"] = relative(path)
        family = classify_municipal(path)
        df["dataset_family"] = family
        if family == "mobility":
            df = normalize_mobility_columns(df)
        rows.append(df)
        report.append(item(path, "OK", len(df), f"Municipal prioritario {city}"))
    if rows:
        outputs["municipios/municipal_prioritario.csv"] = pd.concat(rows, ignore_index=True, sort=False)
    return outputs


def classify_municipal(path: Path) -> str:
    text = str(path).lower()
    if any(token in text for token in ("renda", "renta", "income")):
        return "income"
    if any(token in text for token in ("poblacion", "demografic", "demograf")):
        return "demography"
    if any(token in text for token in ("trafic", "transit", "bizi", "bicic", "acciden")):
        return "mobility"
    if "sostenibilidad" in text:
        return "environment"
    return "other"


def normalize_mobility_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize accident column names across city formats so the pipeline sees a
    consistent schema: fecha, tipo_gravedad, tipo_accidente."""
    df = df.copy()
    # Madrid format: semicolons, fecha=DD/MM/YYYY, severity=lesividad
    if "lesividad" in df.columns and "tipo_gravedad" not in df.columns:
        df = df.rename(columns={"lesividad": "tipo_gravedad"})
    if "fecha" in df.columns:
        parsed = pd.to_datetime(df["fecha"], dayfirst=True, errors="coerce")
        valid = parsed.notna()
        if valid.any():
            df.loc[valid, "fecha"] = parsed[valid].dt.strftime("%Y-%m-%d")
    # Barcelona format: year=nk_any, month=mes_any, day=dia_mes; severity absent
    if "nk_any" in df.columns and "fecha" not in df.columns:
        df["fecha"] = (
            df["nk_any"].astype(str).str.zfill(4)
            + "-"
            + df["mes_any"].astype(str).str.zfill(2)
            + "-"
            + df["dia_mes"].astype(str).str.zfill(2)
        )
    if "descripcio_tipus_accident" in df.columns and "tipo_accidente" not in df.columns:
        df = df.rename(columns={"descripcio_tipus_accident": "tipo_accidente"})
    # Ensure tipo_gravedad exists so monthly observations can be built from any city
    if "fecha" in df.columns and "tipo_gravedad" not in df.columns:
        df["tipo_gravedad"] = "Sin clasificar"
    return df


def item(path: Path, status: str, rows: int, note: str) -> dict[str, Any]:
    return {
        "file": relative(path),
        "status": status,
        "rows": int(rows),
        "note": note,
    }


if __name__ == "__main__":
    raise SystemExit(main())
