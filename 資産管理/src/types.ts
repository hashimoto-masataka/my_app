export type Category = '預金' | '国内株式' | '米国株式' | '暗号資産' | '投資信託' | 'その他';
export type Owner = '夫' | '妻' | '共有';
export type Asset = { id: number; name: string; category: Category; amount: number; previous: number; symbol: string; owner: Owner; husbandShare: number };
export type HistoryRecord = { month: string; husband: number; wife: number };
export type Page = 'dashboard' | 'assets' | 'income' | 'history' | 'settings';
export type CashflowItem = { id:number; type:'income'|'expense'; name:string; owner:Owner; amount:number; day?:number };
