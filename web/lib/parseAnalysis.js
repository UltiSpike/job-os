// 解析后端流式分析的 delimited text 格式
// SCORE: 75
// STRENGTHS:
// - foo
// - bar
// GAPS:
// - baz
// SUGGESTIONS:
// xxx
// TOPICS: a, b, c
//
// 流式调用：每次给最新的 full text，返回最新的 partial parse 结果
export function parseAnalysis(text) {
  const out = {
    score: null,
    strengths: [],
    gaps: [],
    suggestions: '',
    topics_touched: [],
  };
  if (!text) return out;

  const lines = text.split('\n');
  let section = null;
  const sugBuf = [];

  for (const raw of lines) {
    const line = raw.trim();
    if (!line) continue;

    // section 头部
    const m = line.match(/^(SCORE|STRENGTHS|GAPS|SUGGESTIONS|TOPICS)\s*:\s*(.*)$/i);
    if (m) {
      section = m[1].toUpperCase();
      const rest = m[2].trim();
      if (section === 'SCORE') {
        const n = parseInt(rest, 10);
        if (!isNaN(n)) out.score = n;
      } else if (section === 'TOPICS' && rest) {
        out.topics_touched = rest.split(',').map(s => s.trim()).filter(Boolean);
      } else if (section === 'SUGGESTIONS' && rest) {
        sugBuf.push(rest);
      }
      continue;
    }

    // section 内容行
    if (section === 'STRENGTHS' && (line.startsWith('-') || line.startsWith('・') || line.startsWith('•'))) {
      out.strengths.push(line.replace(/^[-・•]\s*/, ''));
    } else if (section === 'GAPS' && (line.startsWith('-') || line.startsWith('・') || line.startsWith('•'))) {
      out.gaps.push(line.replace(/^[-・•]\s*/, ''));
    } else if (section === 'SUGGESTIONS') {
      sugBuf.push(line);
    }
  }
  out.suggestions = sugBuf.join(' ').trim();
  return out;
}
