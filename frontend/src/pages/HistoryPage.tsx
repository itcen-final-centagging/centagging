import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Clock3,
  ImageOff,
  Plus,
  Tag,
} from 'lucide-react';
import { Link } from 'react-router-dom';

import { Button } from '@/commons/components/Button';
import {
  APPROVAL_STATUS_LABELS,
  APPROVAL_STATUS_STYLES,
} from '@/features/approvals/constants/approvalStatus';
import { fetchTaggingHistory } from '@/features/tagging/api/tagging';
import { HistorySkuThumbnail } from '@/features/tagging/components/HistorySkuThumbnail';
import { useTaggingWorkflow } from '@/features/tagging/hooks/useTaggingWorkflow';
import type { TaggingHistory } from '@/features/tagging/types';
import { groupTaggingHistoryByScene } from '@/features/tagging/utils/history';
import { cn } from '@/lib/utils';

const HistorySceneThumbnail = ({
  imageName,
  imageUrl,
}: {
  imageName: string;
  imageUrl: string | null;
}) => {
  const [hasFailed, setHasFailed] = useState(false);
  if (!imageUrl || hasFailed) {
    return (
      <span className="flex size-16 shrink-0 items-center justify-center rounded-lg bg-neutral-100 text-text-secondary">
        <ImageOff size={18} />
      </span>
    );
  }
  return (
    <img
      alt={`${imageName} 연출 이미지`}
      className="size-16 shrink-0 rounded-lg border border-neutral-200 object-cover"
      onError={() => setHasFailed(true)}
      src={imageUrl}
    />
  );
};

export const HistoryPage = () => {
  const { resetWorkflow } = useTaggingWorkflow();
  const [history, setHistory] = useState<TaggingHistory[]>([]);
  const [historyError, setHistoryError] = useState<string>();
  const [isHistoryLoading, setIsHistoryLoading] = useState(true);
  const [expandedSceneIds, setExpandedSceneIds] = useState<Set<string>>(
    new Set(),
  );
  const historyGroups = useMemo(
    () => groupTaggingHistoryByScene(history),
    [history],
  );

  const loadHistory = useCallback(async (): Promise<void> => {
    setIsHistoryLoading(true);
    setHistoryError(undefined);
    try {
      setHistory(await fetchTaggingHistory());
    } catch (error) {
      setHistoryError(
        error instanceof Error ? error.message : '이력을 불러오지 못했습니다.',
      );
    } finally {
      setIsHistoryLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const toggleScene = (sceneImageId: string) => {
    setExpandedSceneIds((expandedIds) => {
      const nextIds = new Set(expandedIds);
      if (nextIds.has(sceneImageId)) nextIds.delete(sceneImageId);
      else nextIds.add(sceneImageId);
      return nextIds;
    });
  };

  return (
    <div className="px-6 py-6 pb-10">
      <div className="flex items-center gap-2">
        <span className="text-[24px] font-semibold tracking-[-0.02em] text-text-primary">
          가구 태깅
        </span>
        <span className="text-text-secondary">/</span>
        <h1 className="studio-page-title text-[24px] font-semibold tracking-[-0.02em] text-text-primary">
          검수 이력
        </h1>
      </div>
      <p className="mt-1 text-sm leading-6 text-text-secondary">
        저장된 상품 연결과 태깅 결과를 최신순으로 확인합니다.
      </p>
      {isHistoryLoading ? (
        <section className="studio-surface mt-6 flex min-h-60 items-center justify-center px-6 text-sm font-semibold text-text-secondary">
          이력을 불러오는 중입니다.
        </section>
      ) : null}
      {historyError ? (
        <section
          className="mt-6 rounded-md border border-warning-200 bg-warning-50 px-4 py-3 text-sm font-semibold text-warning-700"
          role="alert"
        >
          <p>최신 이력을 불러오지 못했습니다. {historyError}</p>
          <Button className="mt-3" onClick={() => void loadHistory()} size="sm">
            다시 시도
          </Button>
        </section>
      ) : null}
      {history.length === 0 && !historyError && !isHistoryLoading ? (
        <section className="studio-surface mt-6 flex min-h-90 flex-col items-center justify-center px-6 text-center">
          <span className="flex size-16 items-center justify-center rounded-full bg-blue-100 text-blue-700">
            <Clock3 size={28} />
          </span>
          <h2 className="mt-5 text-xl font-bold text-text-primary">
            저장된 검수 이력이 없습니다
          </h2>
          <p className="mt-2 text-sm text-text-secondary">
            새 태깅 작업에서 SKU와 태그를 검수한 후 저장해 주세요.
          </p>
          <Link
            className="mt-5 inline-flex min-h-[42px] items-center justify-center gap-2 rounded-xl border border-blue-700 bg-blue-700 px-[18px] text-sm font-semibold text-white transition-all hover:-translate-y-px hover:border-blue-900 hover:bg-blue-900"
            onClick={resetWorkflow}
            to="/"
          >
            <Plus size={17} />새 태깅 작업
          </Link>
        </section>
      ) : null}
      {history.length > 0 && !isHistoryLoading ? (
        <section className="mt-6 max-w-4xl">
          <p className="mb-3 text-sm font-bold text-text-primary">
            저장된 작업{' '}
            <span className="rounded-full bg-success-50 px-2 py-1 text-xs text-success-600">
              {history.length}건
            </span>
          </p>
          <div className="space-y-3">
            {historyGroups.map((group) => {
              const isExpanded = expandedSceneIds.has(group.id);
              return (
                <section
                  className="studio-surface overflow-hidden"
                  key={group.id}
                >
                  <button
                    aria-expanded={isExpanded}
                    className="studio-panel-hover flex w-full items-center gap-4 p-5 text-left focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary"
                    onClick={() => toggleScene(group.id)}
                    type="button"
                  >
                    <HistorySceneThumbnail
                      imageName={group.imageName}
                      imageUrl={group.imageUrl}
                    />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-base font-extrabold text-neutral-800">
                        {group.imageName}
                      </span>
                      <span className="mt-1 block text-sm text-neutral-500">
                        탐지 객체 {group.records.length}개 · 최근 저장{' '}
                        {group.latestSavedAt}
                      </span>
                    </span>
                    <span className="shrink-0 text-primary">
                      {isExpanded ? (
                        <ChevronUp size={20} />
                      ) : (
                        <ChevronDown size={20} />
                      )}
                    </span>
                  </button>
                  {isExpanded ? (
                    <div className="border-t border-neutral-200 bg-neutral-50 p-3">
                      <div className="space-y-2">
                        {group.records.map((record) => (
                          <Link
                            className="block rounded-lg bg-white p-4 transition-colors hover:bg-primary-20 focus-visible:outline-2 focus-visible:outline-primary"
                            key={record.id}
                            to={`/history/results/${record.id}`}
                          >
                            <div className="flex gap-4">
                              <HistorySkuThumbnail
                                alt={`${record.productName} SKU 썸네일`}
                                imageUrl={record.skuImageUrl}
                              />
                              <div className="min-w-0 flex-1">
                                <div className="flex flex-wrap items-center justify-between gap-2">
                                  <span className="flex items-center gap-2">
                                    <span className="font-mono text-xs font-bold text-primary">
                                      {record.sku}
                                    </span>
                                    {record.approvalStatus ? (
                                      <span
                                        className={cn(
                                          'rounded-full px-2 py-0.5 text-xs font-bold',
                                          APPROVAL_STATUS_STYLES[
                                            record.approvalStatus
                                          ],
                                        )}
                                      >
                                        {
                                          APPROVAL_STATUS_LABELS[
                                            record.approvalStatus
                                          ]
                                        }
                                      </span>
                                    ) : null}
                                  </span>
                                  <span className="flex items-center gap-1 text-xs text-neutral-400">
                                    {record.savedAt} <ChevronRight size={15} />
                                  </span>
                                </div>
                                <h2 className="mt-2 text-base font-extrabold text-neutral-800">
                                  {record.productName}
                                </h2>
                                <p className="mt-1.5 text-sm text-neutral-500">
                                  {record.objectName}
                                </p>
                                <div className="mt-4 flex flex-wrap gap-2">
                                  {record.tags.styleTags.map((tag) => (
                                    <span
                                      className="inline-flex items-center gap-1 rounded-full bg-primary-20 px-2.5 py-1.5 text-xs font-bold text-primary-700"
                                      key={tag}
                                    >
                                      <Tag size={12} />
                                      {tag}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            </div>
                          </Link>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </section>
              );
            })}
          </div>
        </section>
      ) : null}
    </div>
  );
};
