import type { SkuCandidate } from '../types';

type RubricKey = keyof NonNullable<SkuCandidate['rubric']>['breakdown'];

type RubricDefinition = {
  aliases: readonly string[];
  key: RubricKey;
  label: string;
  maximum: number;
};

export type RubricScore = Pick<
  RubricDefinition,
  'key' | 'label' | 'maximum'
> & {
  score: number | null;
};

export const RUBRIC_DEFINITIONS: readonly RubricDefinition[] = [
  {
    aliases: ['구조', 'structure'],
    key: 'structure',
    label: '구조',
    maximum: 30,
  },
  {
    aliases: ['색상', 'color'],
    key: 'color',
    label: '색상',
    maximum: 30,
  },
  {
    aliases: ['디테일', 'detail'],
    key: 'detail',
    label: '디테일',
    maximum: 20,
  },
  {
    aliases: ['맥락', 'context'],
    key: 'context',
    label: '맥락',
    maximum: 20,
  },
];

const normalizeLabel = (label?: string): string =>
  (label ?? '').trim().toLowerCase();

export const getRubricScores = (
  candidate: Pick<SkuCandidate, 'rubric' | 'xaiResult'>,
): RubricScore[] => {
  const criteriaScores = new Map(
    (candidate.xaiResult?.criteria ?? []).map((criterion) => [
      normalizeLabel(criterion.label),
      criterion.score,
    ]),
  );

  return RUBRIC_DEFINITIONS.map(({ aliases, key, label, maximum }) => {
    const criterionScore = aliases
      .map((alias) => criteriaScores.get(normalizeLabel(alias)))
      .find((score) => score !== undefined);

    return {
      key,
      label,
      maximum,
      score: criterionScore ?? candidate.rubric?.breakdown[key] ?? null,
    };
  });
};

export const getRubricTotal = (
  candidate: Pick<SkuCandidate, 'rubric' | 'score' | 'xaiResult'>,
  rubricScores: readonly RubricScore[],
): number | null => {
  if (candidate.score !== null) return candidate.score;
  if (candidate.rubric) return candidate.rubric.totalScore;
  if (rubricScores.some(({ score }) => score === null)) return null;

  return rubricScores.reduce((total, { score }) => total + (score ?? 0), 0);
};
