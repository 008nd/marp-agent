import { afterEach, describe, expect, it, vi } from 'vitest';

vi.mock('aws-amplify/auth', () => ({
  fetchAuthSession: vi.fn(async () => ({
    tokens: {
      accessToken: {
        toString: () => 'token',
      },
    },
  })),
}));

vi.mock('../../config/amplifyOutputs', () => ({
  loadAmplifyOutputs: vi.fn(async () => ({
    custom: {
      agentRuntimeArn: 'arn:aws:bedrock-agentcore:ap-northeast-1:123456789012:runtime/test-runtime',
    },
  })),
}));

import { invokeAgent } from './agentCoreClient';

describe('invokeAgent', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('sends theme in the invocation payload', async () => {
    const encoder = new TextEncoder();
    const fetchMock = vi.fn(async (url?: string, init?: RequestInit) => {
      void url;
      void init;
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode('data: {"type":"done"}\n'));
          controller.enqueue(encoder.encode('data: [DONE]\n'));
          controller.close();
        },
      });

      return new Response(stream, { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);

    const callbacks = {
      onText: vi.fn(),
      onStatus: vi.fn(),
      onMarkdown: vi.fn(),
      onTweetUrl: vi.fn(),
      onToolUse: vi.fn(),
      onError: vi.fn(),
      onComplete: vi.fn(),
    };

    await invokeAgent('prompt', '---\nmarp: true\n---', 'speee', callbacks, 'session-1', 'standard');

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(init.body as string)).toMatchObject({
      prompt: 'prompt',
      markdown: '---\nmarp: true\n---',
      model_type: 'standard',
      theme: 'speee',
    });
  });
});
