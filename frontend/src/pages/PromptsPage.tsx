import { useTranslation } from 'react-i18next'
import PromptList from '@/components/prompts/PromptList'

export default function PromptsPage() {
  const { t } = useTranslation()

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-foreground">{t('prompts.title')}</h1>
        <p className="text-muted-foreground text-sm mt-1">{t('prompts.subtitle')}</p>
      </div>
      <PromptList />
    </div>
  )
}
