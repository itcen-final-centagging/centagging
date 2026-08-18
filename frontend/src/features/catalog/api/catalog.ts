import { createAuthorizationHeaders } from '@/features/auth/api/auth';
import { requestJson } from '@/lib/api-request';

export type CatalogSku = {
  attributes: Record<string, unknown>;
  brand: string | null;
  category: string | null;
  createdAt: string;
  mainImageUrl: string | null;
  price: number | null;
  productName: string;
  skuCode: string;
  skuId: number;
  space: string | null;
  subCategory: string | null;
};

type ApiCatalogSku = {
  attributes: Record<string, unknown>;
  brand: string | null;
  category: string | null;
  created_at: string;
  main_image_url: string | null;
  price: number | null;
  product_name: string;
  sku_code: string;
  sku_id: number;
  space: string | null;
  sub_category: string | null;
};

type CatalogResponse = { items: ApiCatalogSku[] };

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined)?.replace(
    /\/$/,
    '',
  ) ?? '';

const toAssetUrl = (imageUrl: string | null): string | null => {
  if (!imageUrl || /^https?:\/\//.test(imageUrl)) return imageUrl;
  return `${API_BASE_URL}${imageUrl.startsWith('/') ? '' : '/'}${imageUrl}`;
};

const toCatalogSku = (item: ApiCatalogSku): CatalogSku => ({
  attributes: item.attributes,
  brand: item.brand,
  category: item.category,
  createdAt: item.created_at,
  mainImageUrl: toAssetUrl(item.main_image_url),
  price: item.price,
  productName: item.product_name,
  skuCode: item.sku_code,
  skuId: item.sku_id,
  space: item.space,
  subCategory: item.sub_category,
});

/** 시스템에 등록된 SKU의 대표 이미지와 메타데이터를 조회합니다. */
export const fetchCatalogSkus = async (
  session: string,
): Promise<CatalogSku[]> => {
  const response = await requestJson<CatalogResponse>(
    `${API_BASE_URL}/sku/catalog?limit=50`,
    { headers: createAuthorizationHeaders(session) },
  );
  return response.items.map(toCatalogSku);
};
