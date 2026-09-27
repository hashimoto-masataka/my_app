import type { Asset, HistoryRecord } from './types';

export const initialAssets: Asset[] = [
  { id: 1, name: '生活用共同口座', category: '預金', amount: 7200000, previous: 7050000, symbol: '¥', owner: '共有', husbandShare: 50 },
  { id: 2, name: 'S&P 500', category: '投資信託', amount: 5980000, previous: 5660000, symbol: 'S', owner: '夫', husbandShare: 100 },
  { id: 3, name: 'トヨタ自動車', category: '国内株式', amount: 3420000, previous: 3560000, symbol: 'T', owner: '妻', husbandShare: 0 },
  { id: 4, name: 'NVIDIA', category: '米国株式', amount: 4810320, previous: 4300000, symbol: 'N', owner: '夫', husbandShare: 100 },
  { id: 5, name: 'Bitcoin', category: '暗号資産', amount: 3170000, previous: 2980320, symbol: '₿', owner: '妻', husbandShare: 0 },
];

export const monthly = [
  { month: '1月', amount: 19650000 }, { month: '2月', amount: 20120000 },
  { month: '3月', amount: 21480000 }, { month: '4月', amount: 22030000 },
  { month: '5月', amount: 21850000 }, { month: '6月', amount: 22960000 },
  { month: '7月', amount: 23740000 }, { month: '8月', amount: 24580320 },
];

export const initialHistory: HistoryRecord[] = [
  ...monthly.map((m,i)=>({month:`2026-${String(i+1).padStart(2,'0')}`,husband:Math.round(m.amount*.55),wife:Math.round(m.amount*.45)})),
  ...[15100000,15780000,16250000,16920000,17480000,18130000,18490000,18820000,19050000,19380000,19550000,19780000].map((amount,i)=>({month:`2025-${String(i+1).padStart(2,'0')}`,husband:Math.round(amount*.56),wife:Math.round(amount*.44)}))
];

export const yen = (value: number) => `¥${Math.round(value).toLocaleString('ja-JP')}`;
export const pct = (current: number, previous: number) => `${current >= previous ? '+' : ''}${(((current - previous) / previous) * 100).toFixed(1)}%`;
export const ownerAmount = (asset: Asset, owner: '夫' | '妻') => asset.amount * (owner === '夫' ? asset.husbandShare : 100 - asset.husbandShare) / 100;
export const ownerPrevious = (asset: Asset, owner: '夫' | '妻') => asset.previous * (owner === '夫' ? asset.husbandShare : 100 - asset.husbandShare) / 100;
