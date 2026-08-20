import {
  ATTRIBUTE_LABELS,
  CATEGORY_ATTRIBUTE_FIELDS,
  COMMON_ATTRIBUTE_KEYS,
} from '../constants/skuAttributes';

import type { SkuCandidate } from '../types';

/** 값이 비어 있는 속성에 표기할 문구입니다. */
export const EMPTY_ATTRIBUTE_TEXT = '정보 없음';

/** 카탈로그 속성 값을 화면에 그대로 쓸 수 있는 문자열로 바꿉니다. */
export const formatAttributeValue = (value: unknown): string => {
  if (value === null || value === undefined || value === '') {
    return EMPTY_ATTRIBUTE_TEXT;
  }
  if (typeof value === 'boolean') return value ? '있음' : '없음';
  return String(value);
};

type BuildSkuAttributeRowsOptions = {
  /**
   * 라벨/카테고리 정의에 없는 attrs 키까지 모두 이어서 표기할지 여부입니다.
   * 검수 화면처럼 SKU 데이터를 빠짐없이 보여 줘야 하는 곳에서 켭니다.
   */
  includeUnmappedAttrs?: boolean;
};

/**
 * SKU 상세 속성을 표 형태의 [라벨, 값] 행으로 만듭니다.
 * 공통 속성 뒤에 카테고리별 상세 속성을 이어 붙여, 추천 화면과 검수 화면이
 * 동일한 기준으로 SKU 상세 데이터를 보여 주도록 합니다.
 */
export const buildSkuAttributeRows = (
  candidate: SkuCandidate,
  fallbackCategory: string | null,
  options: BuildSkuAttributeRowsOptions = {},
): Array<[string, string]> => {
  const category = candidate.category ?? fallbackCategory;
  const attrs = candidate.attrs ?? {};
  const categoryKeys = category
    ? (CATEGORY_ATTRIBUTE_FIELDS[category] ?? [])
    : [];
  const knownKeys = new Set([...COMMON_ATTRIBUTE_KEYS, ...categoryKeys]);
  const extraKeys = options.includeUnmappedAttrs
    ? Object.keys(attrs).filter((key) => !knownKeys.has(key))
    : [];

  return [
    ['카테고리', category ?? '가구'],
    ...[...COMMON_ATTRIBUTE_KEYS, ...categoryKeys, ...extraKeys].map(
      (key): [string, string] => [
        ATTRIBUTE_LABELS[key] ?? key,
        formatAttributeValue(attrs[key]),
      ],
    ),
  ];
};
