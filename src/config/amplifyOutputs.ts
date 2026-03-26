export interface AmplifyOutputs {
  custom?: {
    agentRuntimeArn?: string;
  };
  [key: string]: unknown;
}

declare global {
  interface Window {
    __AMPLIFY_OUTPUTS__?: AmplifyOutputs;
  }
}

let cachedOutputs: AmplifyOutputs | null = null;
let loadingPromise: Promise<AmplifyOutputs> | null = null;

async function fetchAmplifyOutputs(): Promise<AmplifyOutputs> {
  const response = await fetch('/amplify_outputs.json', {
    headers: {
      Accept: 'application/json',
    },
  });

  if (!response.ok) {
    throw new Error('amplify_outputs.json の読み込みに失敗しました');
  }

  return (await response.json()) as AmplifyOutputs;
}

export async function loadAmplifyOutputs(): Promise<AmplifyOutputs> {
  if (cachedOutputs) {
    return cachedOutputs;
  }

  if (typeof window !== 'undefined' && window.__AMPLIFY_OUTPUTS__) {
    cachedOutputs = window.__AMPLIFY_OUTPUTS__;
    return cachedOutputs;
  }

  if (!loadingPromise) {
    loadingPromise = fetchAmplifyOutputs().then((outputs) => {
      cachedOutputs = outputs;
      return outputs;
    });
  }

  return loadingPromise;
}
