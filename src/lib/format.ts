/* 展示层的数字/时间格式化工具（纯函数，便于测试）。
 * 只负责把原始值渲染成人话字符串，不改任何后端数据。 */

/** 大数字千分位：2161 → "2,161"。 */
export function fmtInt(n: number): string {
  if (!Number.isFinite(n)) return '0';
  return Math.round(n).toLocaleString('en-US');
}

/** 百分比整数：0.994 → "99%"，传入已是百分数则原样取整。分母为 0 返回 0。 */
export function pct(part: number, whole: number): number {
  if (!whole || whole <= 0) return 0;
  return Math.round((part / whole) * 100);
}

/** 相对时间人话化：刚刚 / N 分钟前 / N 小时前 / N 天前 / 具体日期。 */
export function relTime(iso: string | number | Date | undefined | null, now: number = Date.now()): string {
  if (iso == null) return '';
  const t = typeof iso === 'number' ? iso : new Date(iso).getTime();
  if (!Number.isFinite(t)) return '';
  const diff = Math.max(0, now - t);
  const min = Math.floor(diff / 60000);
  if (min < 1) return '刚刚';
  if (min < 60) return `${min} 分钟前`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} 小时前`;
  const day = Math.floor(hr / 24);
  if (day < 7) return `${day} 天前`;
  const d = new Date(t);
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${mm}-${dd}`;
}

/** 从冗长的数据源全名里取一个短标题：括号/连字符前的主体。
 *  "Gitea (代码托管 / DevOps 平台, 远端US94)" → "Gitea" */
export function shortSourceName(name: string | null | undefined): string {
  if (!name) return '未知系统';
  const cut = name.split(/[（(·]/)[0].trim();
  return cut || name.trim();
}
