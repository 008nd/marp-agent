import type { AgentCoreCallbacks, ModelType } from '../api/agentCoreClient';
import type { ShareResult } from '../api/exportClient';

export async function exportPdfMock(markdown: string, theme: string = 'gradient'): Promise<Blob> {
  void theme;
  await new Promise((resolve) => setTimeout(resolve, 1000));
  return new Blob([markdown], { type: 'text/markdown' });
}

export async function exportPptxMock(markdown: string, theme: string = 'gradient'): Promise<Blob> {
  void theme;
  await new Promise((resolve) => setTimeout(resolve, 1000));
  return new Blob([markdown], { type: 'text/markdown' });
}

export async function exportEditablePptxMock(markdown: string, theme: string = 'gradient'): Promise<Blob> {
  void theme;
  await new Promise((resolve) => setTimeout(resolve, 1000));
  return new Blob([markdown], { type: 'text/markdown' });
}

export async function shareSlideMock(markdown: string, theme: string = 'gradient'): Promise<ShareResult> {
  void markdown;
  void theme;
  await new Promise((resolve) => setTimeout(resolve, 1000));
  const mockSlideId = crypto.randomUUID();
  return {
    url: `https://mock.cloudfront.net/slides/${mockSlideId}/index.html`,
    expiresAt: Math.floor(Date.now() / 1000) + 7 * 24 * 60 * 60,
  };
}

export async function invokeAgentMock(
  prompt: string,
  currentMarkdown: string,
  theme: string,
  callbacks: AgentCoreCallbacks,
  sessionId?: string,
  modelType: ModelType = 'standard',
): Promise<void> {
  void currentMarkdown;
  void sessionId;
  void modelType;
  const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

  const thinkingText = `${prompt}についてスライドを作成しますね。\n\n構成を考えています...`;
  for (const char of thinkingText) {
    callbacks.onText(char);
    await sleep(20);
  }

  callbacks.onToolUse('output_slide');
  await sleep(1000);

  const sampleMarkdown = `---
marp: true
theme: ${theme}
size: 16:9
paginate: true
---

# ${prompt}

サンプルスライド

---

## スライド 2

- ポイント 1
- ポイント 2
- ポイント 3

---

<!-- _class: end -->
<!-- _paginate: skip -->
# Thank you!
`;

  callbacks.onMarkdown(sampleMarkdown);
  callbacks.onText('\n\nスライドを生成しました！プレビュータブで確認できます。');

  if (prompt.includes('シェア') || prompt.includes('ツイート')) {
    callbacks.onToolUse('generate_tweet_url');
    await sleep(500);
    const tweetText = encodeURIComponent('#パワポ作るマン でスライドを作ってみました。これは便利！ pawapo.minoruonda.com');
    callbacks.onTweetUrl?.(`https://twitter.com/intent/tweet?text=${tweetText}`);
  }

  callbacks.onComplete();
}
