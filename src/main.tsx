import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Amplify } from 'aws-amplify'
import { I18n } from 'aws-amplify/utils'
import { translations } from '@aws-amplify/ui-react'
import outputs from '../amplify_outputs.json'
import './index.css'
import App from './App.tsx'

Amplify.configure(outputs)
I18n.putVocabularies(translations)
I18n.setLanguage('ja')

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
