import { useState, type FormEvent } from 'react';
import { ArrowLeft, ArrowRight, Check, Search, SearchX } from 'lucide-react';

import { Button } from '@/commons/components/Button';
import { FurnitureArtwork } from '@/features/tagging/components/FurnitureArtwork';
import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';
import type { SkuCandidate } from '@/features/tagging/types';
import { cn } from '@/lib/utils';

interface CatalogItemProps {
  item: SkuCandidate;
}

const CatalogItem = ({ item }: CatalogItemProps) => {
  const { selectSku, selectedSku } = useTaggingWorkflow();
  const isSelected = selectedSku?.sku === item.sku;

  const handleSkuSelect = (): void => {
    selectSku(item);
  };

  return (
    <article
      className={cn(
        'grid gap-4 border-b border-neutral-100 py-4 last:border-b-0 sm:grid-cols-[68px_minmax(0,1.25fr)_minmax(0,1fr)_auto] sm:items-center',
        isSelected && 'rounded-lg bg-primary-20 px-3',
      )}
    >
      <FurnitureArtwork
        className="h-[58px]"
        imageUrl={item.imageUrl}
        kind={item.kind}
      />
      <div>
        <h2 className="text-sm font-extrabold text-neutral-800">{item.name}</h2>
        <p className="mt-1 font-mono text-xs font-bold text-neutral-400">
          {item.sku}
        </p>
      </div>
      <p className="text-xs leading-5 text-neutral-500">
        {item.color ?? 'null'} · {item.material ?? 'null'}
      </p>
      <Button
        onClick={handleSkuSelect}
        size="sm"
        startDecorator={isSelected ? <Check size={14} /> : undefined}
        variant={isSelected ? 'primary-solid' : 'neutral-outlined'}
      >
        {isSelected ? '선택됨' : '선택'}
      </Button>
    </article>
  );
};

export const CatalogPanel = () => {
  const { catalogResults, changeStage, searchCatalog, workflowError } =
    useTaggingWorkflow();
  const [query, setQuery] = useState('');
  const [hasSearched, setHasSearched] = useState(false);
  const [searchError, setSearchError] = useState<string>();

  const handleSearch = async (
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> => {
    event.preventDefault();
    if (!query.trim()) {
      setSearchError('검색어를 입력해 주세요.');
      return;
    }
    setSearchError(undefined);
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

  return (
    <section className="studio-surface p-6">
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
      {searchError ? (
        <p className="mt-2 text-xs text-danger-600">{searchError}</p>
      ) : null}
      {workflowError ? (
        <p className="mt-2 text-xs text-danger-600">{workflowError}</p>
      ) : null}
      <div className="mt-6">
        {hasSearched && catalogResults.length > 0 ? (
          <>
            <p className="mb-2 text-sm font-extrabold text-neutral-800">
              검색 결과{' '}
              <span className="rounded-full bg-success-50 px-2 py-1 text-xs text-success-600">
                {catalogResults.length}건
              </span>
            </p>
            {catalogResults.map((item) => (
              <CatalogItem item={item} key={item.sku} />
            ))}
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
    </section>
  );
};
