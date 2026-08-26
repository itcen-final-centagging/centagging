import {
  ATTRIBUTE_LABELS,
  CATEGORY_ATTRIBUTE_FIELDS,
  COMMON_ATTRIBUTE_KEYS,
} from '../constants/skuAttributes';

import type { SkuCandidate } from '../types';

/** 값이 비어 있는 속성에 표기할 문구입니다. */
export const EMPTY_ATTRIBUTE_TEXT = '정보 없음';

/**
 * XAI가 영문으로 반환할 수 있는 대표 시각 속성값의 화면 표시명입니다.
 *
 * 신규 응답은 프롬프트에서 한국어를 요구하지만, 기존 저장 응답과 모델의
 * 간헐적인 영문 응답도 동일하게 표시할 수 있도록 프론트에서 보정합니다.
 */
const ATTRIBUTE_VALUE_LABELS: Record<string, string> = {
  true: '있음',
  false: '없음',
  yes: '있음',
  no: '없음',
  black: '블랙',
  white: '화이트',
  beige: '베이지',
  navy: '네이비',
  khaki: '카키',
  gray: '그레이',
  grey: '그레이',
  brown: '브라운',
  red: '레드',
  yellow: '옐로우',
  blue: '블루',
  pink: '핑크',
  purple: '퍼플',
  green: '그린',
  orange: '오렌지',
  modern: '모던',
  classic: '클래식',
  vintage: '빈티지',
  minimal: '미니멀',
  minimalist: '미니멀',
  natural: '내추럴',
  luxury: '럭셔리',
  industrial: '인더스트리얼',
  scandinavian: '북유럽',
  lovely: '러블리',
  plain: '무지',
  solid: '무지',
  wood_grain: '우드그레인',
  marble: '마블',
  rattan_weaving: '라탄·위빙',
  fabric_texture: '패브릭 텍스처',
  graphic: '그래픽',
  wood: '원목',
  solid_wood: '원목',
  engineered_wood: '가공목',
  metal: '금속',
  steel: '철제/스틸',
  plastic: '플라스틱',
  rattan: '라탄',
  leather: '가죽',
  genuine_leather: '천연가죽',
  faux_leather: '인조가죽',
  fabric: '패브릭',
  suede: '스웨이드',
  mesh: '메쉬',
  velvet: '벨벳',
  glass: '유리',
  fabric_metal: '패브릭·금속',
  side_chair: '인테리어의자',
  stool: '스툴·벤치',
  bean_bag: '빈백',
  armchair: '안락의자',
  rocking_chair: '흔들의자',
  office_chair: '학생·사무용의자',
  gaming_chair: '게이밍의자',
  floor_chair: '좌식의자',
  bar_chair: '바체어',
  footstool: '발받침',
};

/** 카탈로그 및 XAI 속성 값을 한글 화면 표시 문자열로 바꿉니다. */
export const formatAttributeValue = (value: unknown): string => {
  if (value === null || value === undefined || value === '') {
    return EMPTY_ATTRIBUTE_TEXT;
  }
  if (typeof value === 'boolean') return value ? '있음' : '없음';

  const text = String(value).trim();
  const normalized = text.toLowerCase().replace(/[\s-]+/g, '_');
  return ATTRIBUTE_VALUE_LABELS[normalized] ?? text;
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
