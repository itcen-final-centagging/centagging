import { NeutralPalette, PrimaryPalette } from './palette';

export const Semantic = {
  background: {
    body: '#ffffff',
    level0: NeutralPalette[50],
    surface: NeutralPalette[20],
  },
  primary: {
    solid: PrimaryPalette[600],
    hover: PrimaryPalette[700],
    soft: PrimaryPalette[20],
  },
  text: {
    primary: NeutralPalette[800],
    secondary: NeutralPalette[600],
    tertiary: NeutralPalette[500],
  },
} as const;
