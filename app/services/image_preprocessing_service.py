"""융합 임베딩과 VLM 속성 추출이 공유하는 이미지 전처리 Module입니다."""

from __future__ import annotations

import dataclasses

import cv2
import numpy as np
from PIL import Image, ImageOps

from app.core import config


@dataclasses.dataclass(frozen=True)
class QualityDiagnostics:
    """저화질 복구 적용 여부와 측정값입니다."""

    applied: bool
    laplacian_variance: float
    denoise_h: int | None = None
    unsharp_amount: float | None = None


@dataclasses.dataclass(frozen=True)
class LightingDiagnostics:
    """조명 보정 적용 여부와 입력 조도 측정값입니다."""

    applied: bool
    level: str
    median_luminance: float
    dark_pixel_fraction: float
    gamma: float | None = None
    clahe_clip_limit: float | None = None


@dataclasses.dataclass(frozen=True)
class PreprocessDiagnostics:
    """전처리 결과를 평가·관측하기 위한 진단값입니다."""

    quality: QualityDiagnostics
    lighting: LightingDiagnostics
    resized: bool


@dataclasses.dataclass(frozen=True)
class PreprocessResult:
    """전처리된 RGB 이미지와 진단값입니다."""

    image: Image.Image
    diagnostics: PreprocessDiagnostics


def preprocess_for_embedding(
    image: Image.Image,
    settings: config.Settings,
) -> PreprocessResult:
    """임베딩과 속성 추출에 쓸 이미지 한 장을 결정적으로 전처리합니다."""
    normalized = ImageOps.exif_transpose(image).convert("RGB")
    quality_image, quality = _improve_low_quality(normalized, settings)
    lighting_image, lighting = _correct_lighting(quality_image, settings)
    resized_image = (
        _fit_image(lighting_image, settings.image_max_side)
        if settings.image_preprocess_enabled
        else lighting_image
    )

    return PreprocessResult(
        image=resized_image,
        diagnostics=PreprocessDiagnostics(
            quality=quality,
            lighting=lighting,
            resized=resized_image.size != lighting_image.size,
        ),
    )


def _improve_low_quality(
    image: Image.Image,
    settings: config.Settings,
) -> tuple[Image.Image, QualityDiagnostics]:
    """Laplacian variance가 낮은 이미지에만 로컬 복구를 적용합니다."""
    array = np.asarray(image)
    gray = cv2.cvtColor(array, cv2.COLOR_RGB2GRAY)
    variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    if (
        not settings.image_preprocess_enabled
        or variance >= settings.quality_blur_laplacian_threshold
    ):
        return image, QualityDiagnostics(
            applied=False,
            laplacian_variance=round(variance, 2),
        )

    bgr = cv2.cvtColor(array, cv2.COLOR_RGB2BGR)
    denoised = cv2.fastNlMeansDenoisingColored(
        bgr,
        None,
        h=settings.quality_denoise_h,
        hColor=settings.quality_denoise_h,
        templateWindowSize=7,
        searchWindowSize=21,
    )
    lab = cv2.cvtColor(denoised, cv2.COLOR_BGR2LAB)
    luminance, channel_a, channel_b = cv2.split(lab)
    blurred = cv2.GaussianBlur(
        luminance,
        (0, 0),
        sigmaX=settings.quality_unsharp_sigma,
    )
    sharpened = cv2.addWeighted(
        luminance,
        1.0 + settings.quality_unsharp_amount,
        blurred,
        -settings.quality_unsharp_amount,
        0,
    )
    repaired = cv2.cvtColor(
        cv2.merge((sharpened, channel_a, channel_b)),
        cv2.COLOR_LAB2RGB,
    )
    return Image.fromarray(repaired), QualityDiagnostics(
        applied=True,
        laplacian_variance=round(variance, 2),
        denoise_h=settings.quality_denoise_h,
        unsharp_amount=settings.quality_unsharp_amount,
    )


def _correct_lighting(
    image: Image.Image,
    settings: config.Settings,
) -> tuple[Image.Image, LightingDiagnostics]:
    """어두운 입력에만 감마 보정과 CLAHE를 적용합니다."""
    median, dark_fraction = _measure_lighting(
        image,
        settings.lighting_dark_pixel_value,
    )
    severe = (
        median < settings.lighting_severe_median
        or dark_fraction > settings.lighting_severe_dark_fraction
    )
    moderate = (
        median < settings.lighting_moderate_median
        or dark_fraction > settings.lighting_moderate_dark_fraction
    )
    if not settings.image_preprocess_enabled or not (severe or moderate):
        return image, LightingDiagnostics(
            applied=False,
            level="none",
            median_luminance=median,
            dark_pixel_fraction=round(dark_fraction, 4),
        )

    level = "severe" if severe else "moderate"
    gamma = (
        settings.lighting_severe_gamma
        if severe
        else settings.lighting_moderate_gamma
    )
    lab = cv2.cvtColor(np.asarray(image), cv2.COLOR_RGB2LAB)
    luminance, channel_a, channel_b = cv2.split(lab)
    gamma_lut = np.clip(
        ((np.arange(256, dtype=np.float32) / 255.0) ** gamma) * 255.0,
        0,
        255,
    ).astype(np.uint8)
    luminance = cv2.LUT(luminance, gamma_lut)
    clahe = cv2.createCLAHE(
        clipLimit=settings.lighting_clahe_clip_limit,
        tileGridSize=(
            settings.lighting_clahe_grid_size,
            settings.lighting_clahe_grid_size,
        ),
    )
    luminance = clahe.apply(luminance)
    corrected = cv2.cvtColor(
        cv2.merge((luminance, channel_a, channel_b)),
        cv2.COLOR_LAB2RGB,
    )
    return Image.fromarray(corrected), LightingDiagnostics(
        applied=True,
        level=level,
        median_luminance=median,
        dark_pixel_fraction=round(dark_fraction, 4),
        gamma=gamma,
        clahe_clip_limit=settings.lighting_clahe_clip_limit,
    )


def _measure_lighting(
    image: Image.Image,
    dark_pixel_value: int,
) -> tuple[float, float]:
    """휘도 중앙값과 어두운 픽셀 비율을 계산합니다."""
    histogram = ImageOps.grayscale(image).histogram()
    pixels = max(1, sum(histogram))
    midpoint = (pixels + 1) // 2
    running = 0
    median = 0
    for value, count in enumerate(histogram):
        running += count
        if running >= midpoint:
            median = value
            break
    dark_count = sum(histogram[:dark_pixel_value])
    return float(median), dark_count / pixels


def _fit_image(image: Image.Image, maximum_side: int) -> Image.Image:
    """긴 변이 최대 크기를 초과할 때만 종횡비를 유지해 축소합니다."""
    if maximum_side <= 0 or max(image.size) <= maximum_side:
        return image
    return ImageOps.contain(image, (maximum_side, maximum_side), Image.LANCZOS)
