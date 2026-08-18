import { useEffect, useMemo, useState } from 'react';
import { ImageOff, Images, PackageSearch, Tags } from 'lucide-react';

import { useAuth } from '@/features/auth/hooks/useAuth';
import {
  fetchCatalogSkus,
  type CatalogSku,
} from '@/features/catalog/api/catalog';

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

  useEffect(() => {
    if (!user?.session) return undefined;
    let isMounted = true;
    void fetchCatalogSkus(user.session)
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
  }, [user?.session]);

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
          <PackageSearch className="size-8 text-text-quaternary" />
          <h2 className="mt-4 text-xl font-bold text-text-primary">
            등록된 상품이 없습니다
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            상품이 등록되면 대표 이미지와 메타데이터가 이곳에 표시됩니다.
          </p>
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
