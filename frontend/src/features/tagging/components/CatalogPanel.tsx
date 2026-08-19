import { useEffect, useState, type FormEvent } from 'react';
import {ArrowLeft, ArrowRight, Check, ChevronLeft, ChevronRight, Search, SearchX} from 'lucide-react';

import { Button } from '@/commons/components/Button';
import { FurnitureArtwork } from '@/features/tagging/components/FurnitureArtwork';
import { fetchSkuDetail, toCandidateFromDetail, type SkuDetail, } from '@/features/tagging/api/tagging';
import {
  ATTRIBUTE_LABELS,
  CATEGORY_ATTRIBUTE_FIELDS,
  COMMON_ATTRIBUTE_KEYS,
} from '@/features/tagging/constants/skuAttributes';
import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';
import type { SkuCandidate } from '@/features/tagging/types';
import { cn } from '@/lib/utils';

const formatPrice = (price: number | null | undefined): string =>
  price === null || price === undefined
    ? 'null'
    : `${price.toLocaleString('ko-KR')}원`;

const formatCategoryPath = (
  category: string | null,
  subCategory?: string | null,
): string => {
  if (!category) return 'null';
  return subCategory ? `${category} > ${subCategory}` : category;
};

const formatAttributeValue = (value: unknown): string => {
  if (value === null || value === undefined || value === '') return 'null';
  if (typeof value === 'boolean') return value ? '있음' : '없음';
  return String(value);
};

/** 카테고리별 정의된 속성 키만 골라 라벨/값 쌍으로 만듭니다. */
const buildDetailAttributeRows = (
  detail: SkuDetail,
): Array<[string, string]> => {
  const categoryKeys = detail.category
    ? (CATEGORY_ATTRIBUTE_FIELDS[detail.category] ?? [])
    : [];

  return [
    ...COMMON_ATTRIBUTE_KEYS.map(
      (key): [string, string] => [
        ATTRIBUTE_LABELS[key] ?? key,
        formatAttributeValue(detail.attrs[key]),
      ],
    ),
    ...categoryKeys.map(
      (key): [string, string] => [
        ATTRIBUTE_LABELS[key] ?? key,
        formatAttributeValue(detail.attrs[key]),
      ],
    ),
  ];
};

interface CatalogRowProps {
  item: SkuCandidate;
  onOpenDetail: (item: SkuCandidate) => void;
}

const CatalogRow = ({ item, onOpenDetail }: CatalogRowProps) => {
  return (
    <article className="grid grid-cols-[58px_minmax(0,1.4fr)_minmax(0,0.55fr)_minmax(0,0.55fr)_60px] items-center gap-4 border-b border-neutral-100 py-4 last:border-b-0">
      <FurnitureArtwork
        className="h-[58px] w-[58px]"
        imageUrl={item.imageUrl}
        kind={item.kind}
      />
      <div className="min-w-0">
        <p className="truncate text-xs text-neutral-400">
          {formatCategoryPath(item.category, item.subCategory)}
        </p>
        <h2 className="mt-0.5 truncate text-sm font-extrabold text-neutral-800">
          {item.name}
        </h2>
        <p className="mt-1 font-mono text-xs font-bold text-neutral-400">
          {item.sku}
        </p>
      </div>
      <p className="truncate text-xs text-neutral-500">{item.brand ?? 'null'}</p>
      <p className="text-sm font-extrabold text-neutral-800">
        {formatPrice(item.price)}
      </p>
      <button
        className="inline-flex items-center justify-end gap-0.5 text-xs font-bold text-primary hover:underline"
        onClick={() => onOpenDetail(item)}
        type="button"
      >
        상세
        <ChevronRight size={14} />
      </button>
    </article>
  );
};

interface SkuDetailViewProps {
  item: SkuCandidate;
  onBack: () => void;
}

const SkuDetailView = ({ item, onBack }: SkuDetailViewProps) => {
  const { addCatalogSkuToCandidates, selectedSku } = useTaggingWorkflow();
  const [detail, setDetail] = useState<SkuDetail>();
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string>();
  const isSelected = selectedSku?.sku === item.sku;

  useEffect(() => {
    let isCancelled = false;
    setDetail(undefined);
    setLoadError(undefined);
    setIsLoading(true);
    fetchSkuDetail(item.sku)
      .then((result) => {
        if (!isCancelled) setDetail(result);
      })
      .catch((error: unknown) => {
        if (isCancelled) return;
        setLoadError(
          error instanceof Error
            ? error.message
            : 'SKU 상세 정보를 불러오지 못했습니다.',
        );
      })
      .finally(() => {
        if (!isCancelled) setIsLoading(false);
      });
    return () => {
      isCancelled = true;
    };
  }, [item.sku]);

  const handleSkuSelect = (): void => {
    if (!detail) return;
    addCatalogSkuToCandidates(toCandidateFromDetail(detail));
  };

  return (
    <div>
      <button
        className="inline-flex items-center gap-1 text-xs font-bold text-neutral-500 hover:text-neutral-800"
        onClick={onBack}
        type="button"
      >
        <ChevronLeft size={14} />
        검색 결과 · {item.sku}
      </button>

      {isLoading ? (
        <div className="flex min-h-60 items-center justify-center text-sm text-neutral-500">
          불러오는 중...
        </div>
      ) : null}

      {!isLoading && loadError ? (
        <div className="flex min-h-60 flex-col items-center justify-center text-center">
          <h2 className="text-lg font-extrabold text-neutral-800">
            SKU 정보를 불러오지 못했습니다
          </h2>
          <p className="mt-2 text-sm text-neutral-500">{loadError}</p>
        </div>
      ) : null}

      {!isLoading && !loadError && detail ? (
        <>
          <h1 className="mt-3 text-lg font-extrabold text-neutral-800">
            {detail.productName}
          </h1>
          <p className="mt-1 text-xs text-neutral-500">
            {detail.brand ?? 'null'} · {formatPrice(detail.price)} ·{' '}
            {formatCategoryPath(detail.category, detail.subCategory)}
          </p>

          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <div className="rounded-xl border border-neutral-100 p-4">
              <p className="text-xs font-bold text-neutral-500">상품 이미지</p>
              <div className="mt-3 flex items-center justify-center rounded-lg bg-neutral-50 p-4">
                <FurnitureArtwork
                  className="h-56 w-full"
                  imageUrl={detail.imageUrl}
                  kind={item.kind}
                />
              </div>
              <p className="mt-2 text-[11px] text-neutral-400">
                image_url은 MAIN 타입 1장만 제공됩니다.
              </p>
            </div>

            <div className="rounded-xl border border-neutral-100 p-4">
              <p className="text-xs font-bold text-neutral-500">
                SKU 카탈로그 속성
              </p>
              <p className="mt-0.5 text-xs text-neutral-400">
                {formatCategoryPath(detail.category, detail.subCategory)}
              </p>
              <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-3">
                {buildDetailAttributeRows(detail).map(([label, value]) => (
                  <div key={label}>
                    <dt className="text-[11px] text-neutral-400">{label}</dt>
                    <dd className="mt-0.5 text-sm font-bold text-neutral-800">
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>

          <div className="mt-4 rounded-xl border border-neutral-100 p-4">
            <p className="text-xs font-bold text-neutral-500">기본 정보</p>
            <dl className="mt-3 space-y-2">
              <div className="flex items-center justify-between text-sm">
                <dt className="text-neutral-500">SKU 코드</dt>
                <dd className="font-mono font-bold text-neutral-800">
                  {detail.skuCode}
                </dd>
              </div>
              <div className="flex items-center justify-between text-sm">
                <dt className="text-neutral-500">브랜드</dt>
                <dd className="font-bold text-neutral-800">
                  {detail.brand ?? 'null'}
                </dd>
              </div>
              <div className="flex items-center justify-between text-sm">
                <dt className="text-neutral-500">가격</dt>
                <dd className="font-bold text-neutral-800">
                  {formatPrice(detail.price)}
                </dd>
              </div>
            </dl>
            <Button
              className="mt-4"
              fullWidth
              onClick={handleSkuSelect}
              startDecorator={isSelected ? <Check size={16} /> : undefined}
              variant={isSelected ? 'neutral-outlined' : 'primary-solid'}
            >
              {isSelected ? '이 SKU로 선택됨' : '이 SKU 선택'}
            </Button>
          </div>
        </>
      ) : null}
    </div>
  );
};

export const CatalogPanel = () => {
  const { catalogResults, changeStage, searchCatalog, workflowError } =
    useTaggingWorkflow();
  const [query, setQuery] = useState('');
  const [hasSearched, setHasSearched] = useState(false);
  const [searchError, setSearchError] = useState<string>();
  const [detailItem, setDetailItem] = useState<SkuCandidate>();

  const handleSearch = async (
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> => {
    event.preventDefault();
    if (!query.trim()) {
      setSearchError('검색어를 입력해 주세요.');
      return;
    }
    setSearchError(undefined);
    setDetailItem(undefined);
    await searchCatalog(query);
    setHasSearched(true);
  };

  const handleSearchSubmit = (event: FormEvent<HTMLFormElement>): void => {
    void handleSearch(event);
  };

  const handleQueryChange = (query: string): void => {
    setQuery(query);
  };

  const handleRecommendationReturn = (): void => {
    changeStage('recommend');
  };

  const handleOpenDetail = (item: SkuCandidate): void => {
    setDetailItem(item);
  };

  const handleBackToResults = (): void => {
    setDetailItem(undefined);
  };

  return (
    <section className="studio-surface p-6">
      {!detailItem ? (
        <>
          <form
            className="flex flex-col gap-3 sm:flex-row"
            onSubmit={handleSearchSubmit}
          >
            <label className="sr-only" htmlFor="catalog-search">
              상품명 또는 SKU 코드
            </label>
            <div className="relative flex-1">
              <Search
                className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-neutral-400"
                size={18}
              />
              <input
                className="h-11 w-full rounded-md border border-neutral-200 bg-white pl-10 pr-3 text-sm text-neutral-800 outline-none transition-shadow placeholder:text-neutral-400 focus:border-primary focus:ring-3 focus:ring-primary-50"
                id="catalog-search"
                onChange={(event) => handleQueryChange(event.target.value)}
                placeholder="예: 엠버, SOF-EMB-350-GR"
                value={query}
              />
            </div>
            <Button size="lg" type="submit">
              검색
            </Button>
          </form>
          <p className="mt-2 text-xs text-neutral-400">
            텍스트 임베딩 기반 유사도 검색 · 상위 5건 표시
          </p>
          {searchError ? (
            <p className="mt-2 text-xs text-danger-600">{searchError}</p>
          ) : null}
          {workflowError ? (
            <p className="mt-2 text-xs text-danger-600">{workflowError}</p>
          ) : null}
          <div className="mt-6">
            {hasSearched && catalogResults.length > 0 ? (
              <>
                <div
                  className={cn(
                    'grid grid-cols-[58px_minmax(0,1.4fr)_minmax(0,0.55fr)_minmax(0,0.55fr)_60px] gap-4 border-b border-neutral-100 pb-2',
                  )}
                >
                  <span className="text-xs font-bold text-neutral-400">
                    이미지
                  </span>
                  <span className="text-xs font-bold text-neutral-400">
                    카테고리 · 상품명 · SKU 코드
                  </span>
                  <span className="text-xs font-bold text-neutral-400">
                    브랜드
                  </span>
                  <span className="text-xs font-bold text-neutral-400">
                    가격
                  </span>
                  <span />
                </div>
                {catalogResults.map((item) => (
                  <CatalogRow
                    item={item}
                    key={item.sku}
                    onOpenDetail={handleOpenDetail}
                  />
                ))}
                <p className="mt-3 text-xs text-neutral-400">
                  {catalogResults.length}건 표시 (유사도 상위{' '}
                  {catalogResults.length}건, 더 보기 없음)
                </p>
              </>
            ) : null}
            {hasSearched && !workflowError && catalogResults.length === 0 ? (
              <div className="flex min-h-60 flex-col items-center justify-center text-center">
                <span className="flex size-14 items-center justify-center rounded-full bg-primary-20 text-primary">
                  <SearchX size={25} />
                </span>
                <h2 className="mt-4 text-lg font-extrabold text-neutral-800">
                  검색 결과가 없습니다
                </h2>
                <p className="mt-2 text-sm text-neutral-500">
                  다른 SKU 코드나 상품명으로 다시 검색해 주세요.
                </p>
              </div>
            ) : null}
            {!hasSearched ? (
              <div className="flex min-h-60 flex-col items-center justify-center text-center">
                <span className="flex size-14 items-center justify-center rounded-full bg-primary-20 text-primary">
                  <Search size={25} />
                </span>
                <h2 className="mt-4 text-lg font-extrabold text-neutral-800">
                  상품을 검색해 주세요
                </h2>
                <p className="mt-2 text-sm text-neutral-500">
                  SKU 코드 또는 상품명을 입력하면 카탈로그에서 상품을 찾을 수
                  있습니다.
                </p>
              </div>
            ) : null}
          </div>
          <div className="mt-7 grid gap-3 sm:grid-cols-2">
            <Button
              fullWidth
              onClick={handleRecommendationReturn}
              startDecorator={<ArrowLeft size={17} />}
              variant="neutral-outlined"
            >
              추천 목록으로
            </Button>
            <Button
              endDecorator={<ArrowRight size={17} />}
              fullWidth
              onClick={handleRecommendationReturn}
            >
              SKU 처리로 돌아가기
            </Button>
          </div>
        </>
      ) : (
        <SkuDetailView item={detailItem} onBack={handleBackToResults} />
      )}
    </section>
  );
};
