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

import { exportEditablePptx } from './exportClient';

function readBlobAsText(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error);
    reader.readAsText(blob);
  });
}

describe('exportClient', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('requests export_pptx_editable and decodes the blob', async () => {
    const expected = 'hello';
    const base64 = btoa(expected);
    const encoder = new TextEncoder();

    const fetchMock = vi.fn(async (url?: string, init?: RequestInit) => {
      void url;
      void init;
      const stream = new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(`data: {"type":"pptx","data":"${base64}"}\n`));
          controller.close();
        },
      });
      return new Response(stream, { status: 200 });
    });
    vi.stubGlobal('fetch', fetchMock);

    const blob = await exportEditablePptx('---\nmarp: true\n---', 'speee');

    const init = fetchMock.mock.calls[0]?.[1] as RequestInit;
    expect(JSON.parse(init.body as string)).toMatchObject({
      action: 'export_pptx_editable',
      theme: 'speee',
    });
    expect(blob.type).toBe('application/vnd.openxmlformats-officedocument.presentationml.presentation');
    await expect(readBlobAsText(blob)).resolves.toBe(expected);
  });
});
