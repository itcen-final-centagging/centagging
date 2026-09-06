/**
 * SKU 카탈로그 메타데이터 스펙입니다.
 *
 * 백엔드 `app/core/catalog_spec.py`의 정의를 그대로 옮긴 화면용 사본입니다.
 * 검수 화면의 드롭다운 선택지는 이 파일만 참조하므로, 백엔드 스펙이 바뀌면
 * 이 파일도 함께 갱신해야 합니다.
 *
 * 원칙(백엔드와 동일):
 * 1. 속성 key는 영어 snake_case를 사용합니다.
 * 2. 속성 값은 한국어 허용값을 사용합니다.
 * 3. 정의된 허용값 외의 값은 사용하지 않습니다.
 * 4. 존재 여부 속성은 "있음" / "없음" 중 하나를 사용합니다.
 */

/** 색상 허용값과 참고용 HEX입니다. */
export const COLOR: Record<string, string> = {
  블랙: '#000000',
  화이트: '#FFFFFF',
  베이지: '#F5F5DC',
  네이비: '#000080',
  카키: '#708238',
  그레이: '#808080',
  브라운: '#8B4513',
  레드: '#FF0000',
  옐로우: '#FFD700',
  블루: '#0000FF',
  핑크: '#FFC0CB',
  퍼플: '#800080',
  그린: '#008000',
  오렌지: '#FFA500',
};

/** 대분류 -> 고정 소분류 목록입니다. */
export const PRODUCT_CATEGORY: Record<string, string[]> = {
  침대: ['침대프레임', '침대+메트리스', '침대부속가구'],
  매트리스: ['매트리스', '토퍼'],
  '테이블·식탁·책상': [
    '거실·소파테이블',
    '사이드테이블',
    '식탁',
    '책상',
    '좌식테이블',
  ],
  소파: ['일반소파', '리클라이너', '소파베드', '좌식소파', '소파스툴'],
  '서랍·수납장': ['서랍장', '수납장', '캐비닛', '주방수납장', '협탁'],
  '거실장·TV장': ['일반거실장', '높은거실장·사이드보드', 'TV스탠드'],
  선반: ['벽선반', '스탠드선반', '앵글·조립식선반'],
  '진열장·책장': ['진열장,장식장', '책장', '매거진랙'],
  의자: [
    '인테리어의자',
    '스툴·벤치',
    '빈백',
    '안락의자',
    '흔들의자',
    '학생·사무용의자',
    '게이밍의자',
    '좌식의자·자세보정의자',
    '바체어',
    '발받침',
  ],
  '행거·옷장': ['옷장', '붙박이장', '드레스룸', '행거'],
  거울: ['전신거울', '벽거울', '탁상거울'],
  '화장대·콘솔': [
    '일반화장대',
    '수납화장대',
    '좌식·미니화장대',
    '접이식화장대',
    '콘솔',
    '화장대+의자',
  ],
};

/** 대분류 목록입니다. */
export const CATEGORIES: string[] = Object.keys(PRODUCT_CATEGORY);

/** 모든 카테고리에서 공통으로 쓰는 속성의 허용값입니다. */
export const COMMON_ATTRIBUTE: Record<string, string[]> = {
  color: Object.keys(COLOR),
  style: [
    '모던',
    '클래식',
    '빈티지',
    '미니멀',
    '내추럴',
    '럭셔리',
    '인더스트리얼',
    '북유럽',
    '러블리',
  ],
  pattern: ['무지', '우드그레인', '마블', '라탄·위빙', '패브릭 텍스처', '그래픽'],
};

const MATERIAL_FULL = [
  '원목',
  '가공목(MDF 외)',
  '천연대리석',
  '세라믹',
  '철제/스틸',
  '플라스틱',
  '라탄',
  '천연가죽',
  '인조가죽',
  '패브릭',
  '스웨이드',
  '메쉬',
  '벨벳',
];

const MATERIAL_TABLE = MATERIAL_FULL.slice(0, 10);

const SIZE = [
  '싱글(S)',
  '슈퍼싱글(SS)',
  '더블(D)',
  '퀸(Q)',
  '킹(K)',
  '라지킹(LK)',
  '칼킹(CK)',
  '멀티싱글(MS)',
];

const LEVELS = ['1단', '2단', '3단', '4단', '5단 이상'];

/** 존재 여부는 bool 대신 "있음" / "없음"으로 표현합니다. */
const EXISTENCE = ['있음', '없음'];

const WOOD_TONE = ['밝은 우드톤', '중간 우드톤', '어두운 우드톤'];

/** 카테고리별 속성과 허용값입니다. */
export const PRODUCT_ATTRIBUTE: Record<string, Record<string, string[]>> = {
  침대: {
    bed_type: ['성인용', '아동용', '패밀리침대', '수납침대'],
    size: SIZE,
    has_headboard: EXISTENCE,
    frame_type: ['하단오픈형', '하단밀폐형', '하단수납형', '매트일체형'],
    material: MATERIAL_FULL,
    wood_tone: WOOD_TONE,
    head_type: ['일자형', '곡선형', '수납형', '쿠션형', '패널형'],
    base_type: ['통깔판', '멀티깔판'],
    product_type: ['프레임만', '프레임+매트리스'],
  },
  매트리스: {
    mattress_type: ['스프링', '메모리폼', '라텍스', '하이브리드'],
    size: SIZE,
    firmness: ['하드', '미디엄', '소프트'],
    thickness: ['10cm 이하', '11~20cm', '21~30cm', '31cm 이상'],
    features: ['방수커버', '항균', '통풍', '분리형'],
  },
  '테이블·식탁·책상': {
    shape: ['원형', '사각형', '타원형', '기타'],
    top_material: MATERIAL_TABLE,
    frame_material: MATERIAL_TABLE,
    leg_type: ['4다리', 'T자형', 'X자형', '원형베이스'],
    has_storage: EXISTENCE,
    wood_tone: WOOD_TONE,
    seating_capacity: ['2인', '4인', '6인', '8인 이상'],
  },
  소파: {
    sofa_type: [
      '기본형(일자형)',
      '카우치형',
      '코너형',
      '모듈형',
      '좌식형',
      '침대형',
    ],
    material: ['천연가죽', '인조가죽', '스웨이드', '패브릭'],
    has_legs: EXISTENCE,
    has_armrest: EXISTENCE,
    has_headrest: EXISTENCE,
    has_stool: EXISTENCE,
  },
  '서랍·수납장': {
    storage_type: ['서랍장', '수납장', '캐비닛', '주방 수납장', '협탁'],
    drawer_count: LEVELS,
    material: ['원목', '가공목', '금속', '플라스틱', '라탄', '유리'],
    wood_tone: WOOD_TONE,
    door_type: ['미닫이형', '여닫이형', '폴딩형', '플랩형'],
    has_legs: EXISTENCE,
    has_wheels: EXISTENCE,
    has_drawer: EXISTENCE,
  },
  '거실장·TV장': {
    tv_stand_type: [
      '일반형',
      '높은형',
      '확장형',
      '전면수납형(책장형)',
      '스탠드형',
      '이젤형',
    ],
    length: ['120cm 이하', '121~160cm', '161~200cm', '201cm 이상'],
    material: MATERIAL_FULL,
    frame_material: MATERIAL_FULL,
    level_count: LEVELS,
    has_legs: EXISTENCE,
  },
  선반: {
    shelf_type: ['벽선반', '스탠드선반', '앵글·조립식선반'],
    material: MATERIAL_FULL,
    frame_material: MATERIAL_FULL,
    shelf_count: LEVELS,
  },
  '진열장·책장': {
    storage_type: ['진열장', '장식장', '책장', '매거진랙'],
    material: MATERIAL_FULL,
    frame_material: MATERIAL_FULL,
    door_type: ['유리도어', '오픈형', '밀폐형'],
  },
  의자: {
    chair_type: [
      '인테리어의자',
      '스툴·벤치',
      '빈백',
      '안락의자',
      '흔들의자',
      '학생·사무용의자',
      '게이밍의자',
      '좌식의자',
      '자세보정의자',
      '바체어',
      '발받침',
    ],
    material: ['원목', '가공목', '금속', '패브릭', '가죽', '메쉬', '플라스틱'],
    has_wheels: EXISTENCE,
    has_backrest: EXISTENCE,
    has_armrest: EXISTENCE,
  },
  '행거·옷장': {
    wardrobe_type: [
      '긴 옷장',
      '짧은 옷장',
      '서랍 옷장',
      '선반 옷장',
      '선반장',
      '서랍장',
      '액세서리장',
      '이불장',
    ],
    layout_type: ['ㅡ자형', 'ㄷ자형', 'ㄱ자형'],
    mobility_type: ['이동식', '고정식'],
    door_type: ['여닫이', '슬라이딩', '오픈형'],
    storage_features: ['서랍 포함', '선반 포함', '수납 없음'],
    material: ['원목', '가공목', '금속', '플라스틱'],
  },
  거울: {
    installation_type: ['벽걸이형', '스탠드형', '설치형', '부착형'],
    shape: [
      '정사각형',
      '직사각형',
      '원형',
      '타원형',
      '아치형',
      '다각형',
      '유니크형',
    ],
    has_frame: EXISTENCE,
    frame_material: ['원목', '금속', '플라스틱'],
  },
  '화장대·콘솔': {
    vanity_type: [
      '일반형',
      '수납형',
      '좌식형',
      '콘솔형',
      '접이식',
      '전신거울형',
      '벽걸이선반형',
      '미니형',
    ],
    has_mirror: EXISTENCE,
    storage_type: ['서랍형', '선반형', '복합형'],
    material: ['원목', '가공목', '유리', '금속'],
  },
};

/** SKU 코드 생성에 쓰는 카테고리 코드입니다. */
export const CATEGORY_CODE: Record<string, string> = {
  소파: 'SOFA',
  의자: 'CHR',
  '테이블·식탁·책상': 'TBL',
  침대: 'BED',
  매트리스: 'MATT',
  '서랍·수납장': 'DRW',
  '거실장·TV장': 'TV',
  선반: 'SHLF',
  '진열장·책장': 'BOOK',
  '행거·옷장': 'WRD',
  거울: 'MIR',
  '화장대·콘솔': 'VAN',
};

/** 대분류에 속한 소분류 목록을 반환합니다. 정의가 없으면 빈 배열입니다. */
export const getSubCategories = (category: string | null): string[] =>
  category ? (PRODUCT_CATEGORY[category] ?? []) : [];

/** 대분류에서 쓰는 카테고리별 속성명을 정의된 순서대로 반환합니다. */
export const getCategoryAttributeKeys = (category: string | null): string[] =>
  category ? Object.keys(PRODUCT_ATTRIBUTE[category] ?? {}) : [];

/**
 * 해당 대분류와 속성에서 허용되는 값을 반환합니다.
 * 공통 속성을 먼저 찾고, 없으면 카테고리별 속성에서 찾습니다.
 */
export const getAllowedValues = (
  category: string | null,
  attribute: string,
): string[] => {
  const common = COMMON_ATTRIBUTE[attribute];
  if (common) return common;
  if (!category) return [];
  return PRODUCT_ATTRIBUTE[category]?.[attribute] ?? [];
};

/**
 * 소재 선택지를 반환합니다. 카테고리에 material 정의가 없으면(예: 매트리스)
 * 전체 소재 목록으로 대신합니다.
 */
export const getMaterialValues = (category: string | null): string[] => {
  const values = getAllowedValues(category, 'material');
  return values.length > 0 ? values : MATERIAL_FULL;
};

/** 검수 화면에서 소재 계열로 묶어 노출할 속성 키와 표기 순서입니다. */
export const MATERIAL_ATTRIBUTE_KEYS = [
  'material',
  'top_material',
  'frame_material',
] as const;

export interface MaterialAttribute {
  key: string;
  values: string[];
}

/**
 * 대분류에서 쓰는 소재 계열 속성과 허용값을 모두 반환합니다.
 * 예) 테이블·식탁·책상 -> 상판 소재 + 프레임 소재, 거울 -> 프레임 소재.
 * 소재 계열 정의가 하나도 없으면(예: 매트리스) 전체 소재 목록을 가진
 * material 한 건으로 대신합니다.
 */
export const getMaterialAttributes = (
  category: string | null,
): MaterialAttribute[] => {
  const attributes = category ? (PRODUCT_ATTRIBUTE[category] ?? {}) : {};
  const defined = MATERIAL_ATTRIBUTE_KEYS.filter(
    (key) => (attributes[key] ?? []).length > 0,
  ).map((key) => ({ key, values: attributes[key] }));
  return defined.length > 0
    ? defined
    : [{ key: 'material', values: MATERIAL_FULL }];
};

/**
 * 현재 값이 허용값 목록에 없으면 맨 앞에 끼워 넣습니다.
 * 이미 저장된 값이 드롭다운에서 사라지지 않도록 하기 위한 보정입니다.
 */
export const withCurrentValue = (
  values: string[],
  current: string | null | undefined,
): string[] =>
  current && current !== 'null' && !values.includes(current)
    ? [current, ...values]
    : values;
