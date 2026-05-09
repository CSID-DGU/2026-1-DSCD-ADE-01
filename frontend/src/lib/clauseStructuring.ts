export type ClauseField = {
  label: string;
  value: string;
};

export type LeasePaymentTable = {
  intro: string;
  rows: ClauseField[];
};

const FIELD_PATTERNS: Array<{ label: string; regex: RegExp }> = [
  { label: "보증금", regex: /보\s*증\s*금\s*금\s*([0-9,]+)/ },
  { label: "계약금", regex: /계\s*약\s*금\s*금\s*([0-9,]+)/ },
  { label: "중도금", regex: /중\s*도\s*금\s*금\s*([0-9,]+)/ },
  { label: "잔금", regex: /잔\s*금\s*금\s*([0-9,]+)/ },
  { label: "차임(월세)", regex: /차임\(월세\)\s*금\s*([0-9,]+)/ },
  { label: "총 관리비", regex: /총액\s*금\s*([0-9,]+)/ },
  { label: "일반관리비", regex: /일반관리비\s*금\s*([0-9,]+)/ },
  { label: "전기료", regex: /전기료\s*금\s*([0-9,]+)/ },
  { label: "수도료", regex: /수도료\s*금\s*([0-9,]+)/ },
  { label: "가스 사용료", regex: /가스\s*사용료\s*금\s*([0-9,]+)/ },
  { label: "난방비", regex: /난방비\s*금\s*([0-9,]+)/ },
  { label: "인터넷 사용료", regex: /인터넷\s*사용료\s*금\s*([0-9,]+)/ },
  { label: "TV 사용료", regex: /TV\s*사용료\s*금\s*([0-9,]+)/ },
  { label: "기타관리비", regex: /기타관리비\s*금\s*([0-9,]+)/ },
];

function normalize(raw: string): string {
  return raw.replace(/\s+/g, " ").trim();
}

function escapeRegex(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

export function extractClauseFields(text: string): ClauseField[] {
  const src = normalize(text);
  const fields: ClauseField[] = [];
  for (const item of FIELD_PATTERNS) {
    const match = src.match(item.regex);
    const value = match?.[1]?.trim();
    if (value) {
      fields.push({ label: item.label, value: `${value}원` });
    }
  }
  return fields;
}

export function extractLeasePaymentTable(text: string): LeasePaymentTable | null {
  const src = normalize(text);
  const firstKey = "보증금";
  const firstIndex = src.indexOf(firstKey);
  if (firstIndex < 0) return null;

  const intro = src.slice(0, firstIndex).trim();
  const orderedLabels = ["보증금", "계약금", "중도금", "잔금", "차임(월세)", "관리비"];
  const rows: ClauseField[] = [];

  for (let i = 0; i < orderedLabels.length; i += 1) {
    const label = orderedLabels[i];
    const next = orderedLabels[i + 1];
    const pattern = next
      ? new RegExp(`${escapeRegex(label)}\\s*(.*?)\\s*(?=${escapeRegex(next)})`)
      : new RegExp(`${escapeRegex(label)}\\s*(.*)$`);
    const m = src.match(pattern);
    const value = m?.[1]?.trim();
    if (value) rows.push({ label, value });
  }

  if (rows.length === 0) return null;
  return { intro, rows };
}
