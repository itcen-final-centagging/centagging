import { useEffect, useMemo, useState, type FormEvent } from 'react';
import {
  ImageOff,
  Images,
  PackageSearch,
  RotateCcw,
  Search,
  SearchX,
  Tags,
} from 'lucide-react';

import { useAuth } from '@/features/auth/hooks/useAuth';
import {
  fetchCatalogSkus,
  type CatalogFilters,
  type CatalogSku,
} from '@/features/catalog/api/catalog';
import {
  CATEGORIES,
  COMMON_ATTRIBUTE,
  getSubCategories,
} from '@/features/tagging/constants/catalogSpec';

const MIN_SEARCH_QUERY_LENGTH = 2;

const emptyFilters: CatalogFilters = {
  category: '',
  color: '',
  pattern: '',
  q: '',
  style: '',
  subCategory: '',
};

const selectClassName =
  'h-10 rounded-lg border border-border bg-bg-primary px-3 text-sm text-text-primary outline-none transition-colors focus:border-blue-500 disabled:bg-bg-muted disabled:text-text-quaternary';

const metadataLabels: Record<string, string> = {
  color: '색상',
  material: '소재',
  style: '스타일',
};

const formatPrice = (price: number | null): string =>
  price === null ? '가격 미등록' : `${price.toLocaleString('ko-KR')}원`;

const MetadataChips = ({ attributes }: Pick<CatalogSku, 'attributes'>) => {
  const entries = useMemo(
    () => Object.entries(attributes).filter(([, value]) => value !== null),
    [attributes],
  );

  if (entries.length === 0) {
    return <span className="text-xs text-text-quaternary">속성 미등록</span>;
  }

  return (
    <div className="flex flex-wrap gap-1.5">
      {entries.slice(0, 4).map(([key, value]) => (
        <span
          className="rounded-full bg-bg-muted px-2 py-1 text-[11px] font-medium text-text-secondary"
          key={key}
        >
          {metadataLabels[key] ?? key} · {String(value)}
        </span>
      ))}
    </div>
  );
};

export const AdminCatalogPage = () => {
  const { user } = useAuth();
  const [items, setItems] = useState<CatalogSku[]>([]);
  const [error, setError] = useState<string>();
  const [isLoading, setIsLoading] = useState(true);
  const [filters, setFilters] = useState<CatalogFilters>(emptyFilters);
  const [appliedFilters, setAppliedFilters] =
    useState<CatalogFilters>(emptyFilters);
  const [queryError, setQueryError] = useState<string>();

  const hasActiveFilters = Object.values(appliedFilters).some(
    (value) => !!value,
  );

  useEffect(() => {
    if (!user?.session) return undefined;
    let isMounted = true;
    setIsLoading(true);
    void fetchCatalogSkus(user.session, appliedFilters)
      .then((catalog) => {
        if (isMounted) setItems(catalog);
      })
      .catch((requestError: unknown) => {
        if (!isMounted) return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : '등록 상품을 불러오지 못했습니다.',
        );
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });
    return () => {
      isMounted = false;
    };
  }, [user?.session, appliedFilters]);

  const handleCategoryChange = (category: string): void => {
    setFilters((current) => ({ ...current, category, subCategory: '' }));
  };

  const handleSearch = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    const keyword = (filters.q ?? '').trim();
    if (keyword && keyword.length < MIN_SEARCH_QUERY_LENGTH) {
      setQueryError(`검색어는 ${MIN_SEARCH_QUERY_LENGTH}자 이상 입력해주세요.`);
      return;
    }
    setQueryError(undefined);
    setError(undefined);
    setAppliedFilters(filters);
  };

  const handleReset = (): void => {
    setFilters(emptyFilters);
    setQueryError(undefined);
    setError(undefined);
    setAppliedFilters(emptyFilters);
  };

  return (
    <div className="px-6 py-6 pb-10">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <Images className="size-6 text-blue-700" />
            <h1 className="text-[24px] font-semibold tracking-[-0.02em] text-text-primary">
              등록 상품
            </h1>
          </div>
          <p className="mt-1 text-sm leading-6 text-text-secondary">
            시스템 카탈로그에 등록된 대표 이미지와 상품 메타데이터를 확인합니다.
          </p>
        </div>
        <span className="rounded-full bg-bg-muted px-3 py-1.5 text-xs font-bold text-text-secondary">
          {isLoading ? '불러오는 중' : `${items.length}개 SKU`}
        </span>
      </div>

      <form className="studio-surface mt-5 p-4" onSubmit={handleSearch}>
        <div className="grid gap-2 sm:grid-cols-3 lg:grid-cols-5">
          <select
            aria-label="대분류"
            className={selectClassName}
            onChange={(event) => handleCategoryChange(event.target.value)}
            value={filters.category ?? ''}
          >
            <option value="">대분류 전체</option>
            {CATEGORIES.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
          <select
            aria-label="소분류"
            className={selectClassName}
            disabled={!filters.category}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                subCategory: event.target.value,
              }))
            }
            value={filters.subCategory ?? ''}
          >
            <option value="">소분류 전체</option>
            {getSubCategories(filters.category || null).map((subCategory) => (
              <option key={subCategory} value={subCategory}>
                {subCategory}
              </option>
            ))}
          </select>
          <select
            aria-label="색상"
            className={selectClassName}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                color: event.target.value,
              }))
            }
            value={filters.color ?? ''}
          >
            <option value="">색상 전체</option>
            {COMMON_ATTRIBUTE.color.map((color) => (
              <option key={color} value={color}>
                {color}
              </option>
            ))}
          </select>
          <select
            aria-label="스타일"
            className={selectClassName}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                style: event.target.value,
              }))
            }
            value={filters.style ?? ''}
          >
            <option value="">스타일 전체</option>
            {COMMON_ATTRIBUTE.style.map((style) => (
              <option key={style} value={style}>
                {style}
              </option>
            ))}
          </select>
          <select
            aria-label="패턴"
            className={selectClassName}
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                pattern: event.target.value,
              }))
            }
            value={filters.pattern ?? ''}
          >
            <option value="">패턴 전체</option>
            {COMMON_ATTRIBUTE.pattern.map((pattern) => (
              <option key={pattern} value={pattern}>
                {pattern}
              </option>
            ))}
          </select>
        </div>

        <div className="mt-3 flex flex-col gap-2 sm:flex-row">
          <input
            aria-label="SKU 코드 또는 상품명 검색"
            className="h-10 flex-1 rounded-lg border border-border bg-bg-primary px-3 text-sm text-text-primary outline-none transition-colors placeholder:text-text-quaternary focus:border-blue-500"
            onChange={(event) =>
              setFilters((current) => ({
                ...current,
                q: event.target.value,
              }))
            }
            placeholder="SKU 코드 또는 상품명 검색"
            value={filters.q ?? ''}
          />
          <button
            className="inline-flex h-10 items-center justify-center gap-1.5 rounded-lg border border-blue-700 bg-blue-700 px-4 text-sm font-semibold text-white transition-colors hover:bg-blue-900"
            type="submit"
          >
            <Search className="size-4" />
            검색
          </button>
          <button
            className="inline-flex h-10 items-center justify-center gap-1.5 rounded-lg border border-border bg-bg-primary px-4 text-sm font-semibold text-text-secondary transition-colors hover:border-blue-300 hover:bg-bg-hover"
            onClick={handleReset}
            type="button"
          >
            <RotateCcw className="size-4" />
            초기화
          </button>
        </div>

        {queryError ? (
          <p className="mt-2 text-xs font-semibold text-danger-600">
            {queryError}
          </p>
        ) : null}
      </form>

      {error ? (
        <p
          className="mt-5 rounded-xl border border-danger-200 bg-danger-20 px-4 py-3 text-sm font-semibold text-danger-600"
          role="alert"
        >
          {error}
        </p>
      ) : null}

      {!isLoading && !error && items.length === 0 ? (
        <section className="studio-surface mt-6 flex min-h-80 flex-col items-center justify-center px-6 text-center">
          {hasActiveFilters ? (
            <>
              <SearchX className="size-8 text-text-quaternary" />
              <h2 className="mt-4 text-xl font-bold text-text-primary">
                검색 결과가 없습니다
              </h2>
              <p className="mt-2 text-sm text-text-secondary">
                다른 검색 조건으로 시도해보세요.
              </p>
            </>
          ) : (
            <>
              <PackageSearch className="size-8 text-text-quaternary" />
              <h2 className="mt-4 text-xl font-bold text-text-primary">
                등록된 상품이 없습니다
              </h2>
              <p className="mt-2 text-sm text-text-secondary">
                상품이 등록되면 대표 이미지와 메타데이터가 이곳에 표시됩니다.
              </p>
            </>
          )}
        </section>
      ) : null}

      <div className="mt-6 grid gap-4 sm:grid-cols-2 2xl:grid-cols-3">
        {items.map((item) => (
          <article className="studio-surface overflow-hidden" key={item.skuId}>
            <div className="flex h-48 items-center justify-center bg-bg-tertiary p-4">
              {item.mainImageUrl ? (
                <img
                  alt={item.productName}
                  className="h-full w-full object-contain"
                  src={item.mainImageUrl}
                />
              ) : (
                <ImageOff className="size-8 text-text-quaternary" />
              )}
            </div>
            <div className="p-4">
              <p className="font-mono text-[11px] font-bold text-text-tertiary">
                {item.skuCode}
              </p>
              <h2 className="mt-1 truncate text-base font-extrabold text-text-primary">
                {item.productName}
              </h2>
              <p className="mt-2 text-xs leading-5 text-text-secondary">
                {[item.category, item.subCategory]
                  .filter(Boolean)
                  .join(' · ') || '카테고리 미등록'}
              </p>
              <div className="mt-4 flex items-center justify-between gap-3 text-xs text-text-tertiary">
                <span>{item.brand ?? '브랜드 미등록'}</span>
                <span className="font-semibold text-text-secondary">
                  {formatPrice(item.price)}
                </span>
              </div>
              <div className="mt-4 border-t border-border pt-3">
                <div className="mb-2 flex items-center gap-1.5 text-xs font-bold text-text-secondary">
                  <Tags size={13} />
                  등록 메타데이터
                </div>
                <MetadataChips attributes={item.attributes} />
              </div>
            </div>
          </article>
        ))}
      </div>
    </div>
  );
};
