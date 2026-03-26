import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Amplify } from 'aws-amplify'
import { I18n } from 'aws-amplify/utils'
import { translations } from '@aws-amplify/ui-react'
import './index.css'
import App from './App.tsx'
import { loadAmplifyOutputs } from './config/amplifyOutputs'

// モックモード時はAmplify設定をスキップ（ローカル開発用）
const useMock = import.meta.env.VITE_USE_MOCK === 'true'

async function initializeApp() {
  I18n.putVocabularies(translations)
  I18n.setLanguage('ja')

  if (!useMock) {
    const outputs = await loadAmplifyOutputs()
    Amplify.configure(outputs)
  }

  // 設定完了後にレンダリング
  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}

initializeApp()
