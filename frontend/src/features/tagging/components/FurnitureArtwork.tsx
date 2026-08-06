import type { SkuCandidate } from '@/features/tagging/types';
import { cn } from '@/lib/utils';

interface FurnitureArtworkProps {
  className?: string;
  imageUrl?: string;
  kind: SkuCandidate['kind'];
}

export const FurnitureArtwork = ({
  className,
  imageUrl,
  kind,
}: FurnitureArtworkProps) => {
  return (
    <div
      className={cn(
        'relative flex h-28 items-center justify-center overflow-hidden rounded-lg bg-gradient-to-br from-[#f2f5f8] to-[#e4eaf0]',
        className,
      )}
      aria-label={`${kind} 상품 썸네일`}
      role="img"
    >
      {imageUrl ? (
        <img alt="" className="size-full object-contain p-2" src={imageUrl} />
      ) : null}
      {!imageUrl && kind === 'sofa' ? <div className="furniture-sofa" /> : null}
      {!imageUrl && kind === 'table' ? (
        <div className="furniture-table" />
      ) : null}
      {!imageUrl && kind === 'lamp' ? <div className="furniture-lamp" /> : null}
      {!imageUrl && kind === 'chair' ? (
        <div className="furniture-chair" />
      ) : null}
      {!imageUrl && kind === 'cabinet' ? (
        <div className="furniture-cabinet" />
      ) : null}
    </div>
  );
};
