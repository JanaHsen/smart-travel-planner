from __future__ import annotations

import asyncio
import time
from typing import Any

import structlog
from pydantic import BaseModel, Field

log = structlog.get_logger()


# Dataset medians from your Step 1 EDA — used as fallbacks for fields
# the LLM cannot reliably extract from RAG context.
# These match the feature_names ordering in the sidecar JSON exactly.
_FEATURE_DEFAULTS: dict[str, float] = {
    "num_hiking_trails": 25.0,
    "distance_to_nearest_national_park_km": 15.0,
    "extreme_sports_operator_count": 6.0,
    "topographic_elevation_meters": 200.0,
    "outdoor_to_indoor_attraction_ratio": 2.0,
    "spa_and_wellness_center_count": 40.0,
    "distance_to_coastline_or_lake_km": 0.0,
    "noise_and_light_pollution_index": 45.0,
    "sunshine_hours_per_year": 2700.0,
    "density_of_resorts": 1.5,
    "unesco_sites_within_50km": 1.0,
    "museum_and_gallery_count": 20.0,
    "historical_monuments_count": 15.0,
    "age_of_oldest_standing_landmark": 200.0,
    "traditional_markets_count": 5.0,
    "numbeo_cost_of_living_index": 50.0,
    "avg_hostel_nightly_rate_usd": 25.0,
    "avg_inexpensive_meal_cost_usd": 10.0,
    "public_transit_ticket_cost_usd": 1.5,
    "free_attractions_count": 10.0,
    "michelin_star_restaurant_count": 1.0,
    "avg_5_star_hotel_rate_usd": 400.0,
    "luxury_boutique_density": 0.7,
    "yacht_club_and_golf_course_count": 3.0,
    "taxi_cost_per_10km_usd": 18.0,
    "numbeo_safety_index": 75.0,
    "theme_park_and_zoo_count": 2.0,
    "walkability_score": 70.0,
    "family_friendly_hotel_ratio": 0.8,
    "healthcare_quality_index": 75.0,
}


class ClassifyInput(BaseModel):
    """Destination features for travel-style classification.

    All fields are optional with dataset-median defaults so the LLM can supply
    only what it can reliably extract from RAG context. Provide as many real
    values as possible — defaults reduce prediction confidence.
    """
    destination_name: str = Field(..., description="Name of the destination being classified")

    num_hiking_trails: float = Field(default=_FEATURE_DEFAULTS["num_hiking_trails"], ge=0)
    distance_to_nearest_national_park_km: float = Field(default=_FEATURE_DEFAULTS["distance_to_nearest_national_park_km"], ge=0)
    extreme_sports_operator_count: float = Field(default=_FEATURE_DEFAULTS["extreme_sports_operator_count"], ge=0)
    topographic_elevation_meters: float = Field(default=_FEATURE_DEFAULTS["topographic_elevation_meters"], ge=0)
    outdoor_to_indoor_attraction_ratio: float = Field(default=_FEATURE_DEFAULTS["outdoor_to_indoor_attraction_ratio"], ge=0)
    spa_and_wellness_center_count: float = Field(default=_FEATURE_DEFAULTS["spa_and_wellness_center_count"], ge=0)
    distance_to_coastline_or_lake_km: float = Field(default=_FEATURE_DEFAULTS["distance_to_coastline_or_lake_km"], ge=0)
    noise_and_light_pollution_index: float = Field(default=_FEATURE_DEFAULTS["noise_and_light_pollution_index"], ge=0, le=100)
    sunshine_hours_per_year: float = Field(default=_FEATURE_DEFAULTS["sunshine_hours_per_year"], ge=0)
    density_of_resorts: float = Field(default=_FEATURE_DEFAULTS["density_of_resorts"], ge=0)
    unesco_sites_within_50km: float = Field(default=_FEATURE_DEFAULTS["unesco_sites_within_50km"], ge=0)
    museum_and_gallery_count: float = Field(default=_FEATURE_DEFAULTS["museum_and_gallery_count"], ge=0)
    historical_monuments_count: float = Field(default=_FEATURE_DEFAULTS["historical_monuments_count"], ge=0)
    age_of_oldest_standing_landmark: float = Field(default=_FEATURE_DEFAULTS["age_of_oldest_standing_landmark"], ge=0)
    traditional_markets_count: float = Field(default=_FEATURE_DEFAULTS["traditional_markets_count"], ge=0)
    numbeo_cost_of_living_index: float = Field(default=_FEATURE_DEFAULTS["numbeo_cost_of_living_index"], ge=0)
    avg_hostel_nightly_rate_usd: float = Field(default=_FEATURE_DEFAULTS["avg_hostel_nightly_rate_usd"], ge=0)
    avg_inexpensive_meal_cost_usd: float = Field(default=_FEATURE_DEFAULTS["avg_inexpensive_meal_cost_usd"], ge=0)
    public_transit_ticket_cost_usd: float = Field(default=_FEATURE_DEFAULTS["public_transit_ticket_cost_usd"], ge=0)
    free_attractions_count: float = Field(default=_FEATURE_DEFAULTS["free_attractions_count"], ge=0)
    michelin_star_restaurant_count: float = Field(default=_FEATURE_DEFAULTS["michelin_star_restaurant_count"], ge=0)
    avg_5_star_hotel_rate_usd: float = Field(default=_FEATURE_DEFAULTS["avg_5_star_hotel_rate_usd"], ge=0)
    luxury_boutique_density: float = Field(default=_FEATURE_DEFAULTS["luxury_boutique_density"], ge=0)
    yacht_club_and_golf_course_count: float = Field(default=_FEATURE_DEFAULTS["yacht_club_and_golf_course_count"], ge=0)
    taxi_cost_per_10km_usd: float = Field(default=_FEATURE_DEFAULTS["taxi_cost_per_10km_usd"], ge=0)
    numbeo_safety_index: float = Field(default=_FEATURE_DEFAULTS["numbeo_safety_index"], ge=0, le=100)
    theme_park_and_zoo_count: float = Field(default=_FEATURE_DEFAULTS["theme_park_and_zoo_count"], ge=0)
    walkability_score: float = Field(default=_FEATURE_DEFAULTS["walkability_score"], ge=0, le=100)
    family_friendly_hotel_ratio: float = Field(default=_FEATURE_DEFAULTS["family_friendly_hotel_ratio"], ge=0, le=1)
    healthcare_quality_index: float = Field(default=_FEATURE_DEFAULTS["healthcare_quality_index"], ge=0, le=100)


class ClassifyOutput(BaseModel):
    destination_name: str
    label: str
    confidence: float
    all_probabilities: dict[str, float]
    fields_defaulted: list[str]


class ToolError(BaseModel):
    error: str
    retryable: bool


async def classify_destination(
    inp: ClassifyInput,
    *,
    model: Any,
    meta: dict | None = None,
) -> ClassifyOutput | ToolError:
    if model is None or meta is None:
        return ToolError(
            error="ML classifier not loaded; skipping classification",
            retryable=False,
        )

    t0 = time.perf_counter()
    try:
        # Build feature vector in the EXACT order the model was trained on
        feature_names: list[str] = meta["feature_names"]
        inp_dict = inp.model_dump()

        # Track which fields fell back to defaults — useful signal for the LLM
        fields_defaulted: list[str] = []
        for fname in feature_names:
            if inp_dict.get(fname) == _FEATURE_DEFAULTS.get(fname):
                fields_defaulted.append(fname)

        features = [[inp_dict[fname] for fname in feature_names]]

        label_arr = await asyncio.to_thread(model.predict, features)
        proba_arr = await asyncio.to_thread(model.predict_proba, features)

        classes = model.classes_
        prob_dict = {str(cls): float(p) for cls, p in zip(classes, proba_arr[0])}
        predicted = str(label_arr[0])
        confidence = float(prob_dict.get(predicted, 0.0))

        duration_ms = int((time.perf_counter() - t0) * 1000)
        log.info(
            "tool.classify_destination",
            destination=inp.destination_name,
            label=predicted,
            confidence=confidence,
            fields_defaulted=len(fields_defaulted),
            duration_ms=duration_ms,
        )

        return ClassifyOutput(
            destination_name=inp.destination_name,
            label=predicted,
            confidence=confidence,
            all_probabilities=prob_dict,
            fields_defaulted=fields_defaulted,
        )
    except Exception as exc:
        duration_ms = int((time.perf_counter() - t0) * 1000)
        log.error(
            "tool.classify_destination.error",
            destination=inp.destination_name,
            error=str(exc),
            duration_ms=duration_ms,
        )
        return ToolError(error=str(exc), retryable=False)