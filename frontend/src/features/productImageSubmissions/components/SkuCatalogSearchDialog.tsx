import { useState, type FormEvent } from 'react';
import { ChevronLeft, ChevronRight, Search, SearchX, X } from 'lucide-react';

import { Button } from '@/commons/components/Button';
import {
  fetchSkuDetail,
  searchCatalogItems,
  toCandidateFromDetail,
  type SkuDetail,
} from '@/features/tagging/api/tagging';
import { FurnitureArtwork } from '@/features/tagging/components/FurnitureArtwork';
import type { SkuCandidate } from '@/features/tagging/types';

const formatPrice = (price: number | null | undefined): string =>
  price === null || price === undefined
    ? '가격 미입력'
    : `${price.toLocaleString('ko-KR')}원`;

const formatCategoryPath = (
  category: string | null,
  subCategory?: string | null,
): string => {
  if (!category) return '카테고리 미지정';
  return subCategory ? `${category} · ${subCategory}` : category;
};

type SkuCatalogSearchDialogProps = {
  onClose: () => void;
  onSelect: (detail: SkuDetail) => void;
};

export const SkuCatalogSearchDialog = ({
  onClose,
  onSelect,
}: SkuCatalogSearchDialogProps) => {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState<SkuCandidate[]>([]);
  const [hasSearched, setHasSearched] = useState(false);
  const [isSearching, setIsSearching] = useState(false);
  const [searchError, setSearchError] = useState<string>();
  const [detailSkuCode, setDetailSkuCode] = useState<string>();
  const [detail, setDetail] = useState<SkuDetail>();
  const [isDetailLoading, setIsDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string>();

  const handleSearch = async (
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> => {
    event.preventDefault();
    if (!query.trim()) {
      setSearchError('검색어를 입력해 주세요.');
      return;
    }
    setSearchError(undefined);
    setIsSearching(true);
    try {
      const items = await searchCatalogItems(query.trim());
      setResults(items);
      setHasSearched(true);
    } catch (requestError) {
      setSearchError(
        requestError instanceof Error
          ? requestError.message
          : '검색에 실패했습니다.',
      );
    } finally {
      setIsSearching(false);
    }
  };

  const handleOpenDetail = async (skuCode: string): Promise<void> => {
    setDetailSkuCode(skuCode);
    setDetail(undefined);
    setDetailError(undefined);
    setIsDetailLoading(true);
    try {
      const nextDetail = await fetchSkuDetail(skuCode);
      setDetail(nextDetail);
    } catch (requestError) {
      setDetailError(
        requestError instanceof Error
          ? requestError.message
          : 'SKU 상세 정보를 불러오지 못했습니다.',
      );
    } finally {
      setIsDetailLoading(false);
    }
  };

  const handleBackToResults = (): void => {
    setDetailSkuCode(undefined);
    setDetail(undefined);
    setDetailError(undefined);
  };

  const handleSelect = (): void => {
    if (!detail) return;
    onSelect(detail);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4">
      <div className="studio-surface flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden">
        <div className="flex items-center justify-between border-b border-border p-4">
          <h2 className="text-base font-extrabold text-text-primary">
            전체 카탈로그 검색
          </h2>
          <button
            aria-label="닫기"
            className="text-text-tertiary hover:text-text-primary"
            onClick={onClose}
            type="button"
          >
            <X className="size-5" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">
          {detailSkuCode ? (
            <div>
              <button
                className="inline-flex items-center gap-1 text-xs font-bold text-text-tertiary hover:text-text-primary"
                onClick={handleBackToResults}
                type="button"
              >
                <ChevronLeft className="size-3.5" />
                검색 결과로
              </button>

              {isDetailLoading ? (
                <div className="flex min-h-40 items-center justify-center text-sm text-text-tertiary">
                  불러오는 중...
                </div>
              ) : null}

              {!isDetailLoading && detailError ? (
                <p className="mt-4 text-sm text-danger-600">{detailError}</p>
              ) : null}

              {!isDetailLoading && detail ? (
                <>
                  <div className="mt-4 flex items-center justify-center rounded-xl bg-bg-secondary p-4">
                    <FurnitureArtwork
                      className="h-56 w-full"
                      imageUrl={detail.imageUrl}
                      kind={toCandidateFromDetail(detail).kind}
                    />
                  </div>
                  <h3 className="mt-4 text-lg font-extrabold text-text-primary">
                    {detail.productName}
                  </h3>
                  <p className="mt-1 text-xs text-text-tertiary">
                    {formatCategoryPath(detail.category, detail.subCategory)}
                  </p>
                  <dl className="mt-4 space-y-2 rounded-xl bg-bg-secondary p-4 text-sm">
                    <div className="flex items-center justify-between">
                      <dt className="text-text-tertiary">SKU 코드</dt>
                      <dd className="font-mono font-bold text-text-primary">
                        {detail.skuCode}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between">
                      <dt className="text-text-tertiary">브랜드</dt>
                      <dd className="font-bold text-text-primary">
                        {detail.brand ?? '-'}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between">
                      <dt className="text-text-tertiary">가격</dt>
                      <dd className="font-bold text-text-primary">
                        {formatPrice(detail.price)}
                      </dd>
                    </div>
                  </dl>
                  <Button className="mt-4" fullWidth onClick={handleSelect}>
                    이 SKU 선택
                  </Button>
                </>
              ) : null}
            </div>
          ) : (
            <>
              <form
                className="flex flex-col gap-3 sm:flex-row"
                onSubmit={(event) => {
                  void handleSearch(event);
                }}
              >
                <label className="sr-only" htmlFor="sku-catalog-search">
                  상품명 또는 SKU 코드
                </label>
                <div className="relative flex-1">
                  <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-text-quaternary" />
                  <input
                    className="h-10 w-full rounded-lg border border-border bg-bg-primary pl-9 pr-3 text-sm text-text-primary outline-none transition-colors focus:border-blue-500"
                    id="sku-catalog-search"
                    onChange={(event) => setQuery(event.target.value)}
                    placeholder="예: 엠버 소파, SOF-EMB-350-GR"
                    value={query}
                  />
                </div>
                <Button disabled={isSearching} type="submit">
                  {isSearching ? '검색 중' : '검색'}
                </Button>
              </form>
              <p className="mt-2 text-xs text-text-tertiary">
                텍스트 임베딩 기반 유사도 검색 · 상위 5건 표시
              </p>
              {searchError ? (
                <p className="mt-2 text-xs text-danger-600">{searchError}</p>
              ) : null}

              <div className="mt-5">
                {hasSearched && results.length > 0
                  ? results.map((item) => (
                      <button
                        className="flex w-full items-center gap-3 border-b border-border py-3 text-left last:border-b-0 hover:bg-bg-hover"
                        key={item.sku}
                        onClick={() => {
                          void handleOpenDetail(item.sku);
                        }}
                        type="button"
                      >
                        <FurnitureArtwork
                          className="h-14 w-14 shrink-0"
                          imageUrl={item.imageUrl}
                          kind={item.kind}
                        />
                        <div className="min-w-0 flex-1">
                          <p className="truncate text-xs text-text-tertiary">
                            {formatCategoryPath(
                              item.category,
                              item.subCategory,
                            )}
                          </p>
                          <p className="mt-0.5 truncate text-sm font-bold text-text-primary">
                            {item.name}
                          </p>
                          <p className="mt-0.5 font-mono text-[11px] text-text-tertiary">
                            {item.sku}
                          </p>
                        </div>
                        <p className="shrink-0 text-sm font-bold text-text-secondary">
                          {formatPrice(item.price)}
                        </p>
                        <ChevronRight className="size-4 shrink-0 text-text-quaternary" />
                      </button>
                    ))
                  : null}

                {hasSearched && !searchError && results.length === 0 ? (
                  <div className="flex min-h-40 flex-col items-center justify-center text-center">
                    <SearchX className="size-8 text-text-quaternary" />
                    <p className="mt-3 text-sm font-bold text-text-primary">
                      검색 결과가 없습니다
                    </p>
                    <p className="mt-1 text-xs text-text-secondary">
                      다른 SKU 코드나 상품명으로 다시 검색해 주세요.
                    </p>
                  </div>
                ) : null}

                {!hasSearched ? (
                  <div className="flex min-h-40 flex-col items-center justify-center text-center">
                    <Search className="size-8 text-text-quaternary" />
                    <p className="mt-3 text-sm font-bold text-text-primary">
                      상품을 검색해 주세요
                    </p>
                    <p className="mt-1 text-xs text-text-secondary">
                      SKU 코드 또는 상품명을 입력하면 카탈로그에서 찾을 수
                      있습니다.
                    </p>
                  </div>
                ) : null}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
