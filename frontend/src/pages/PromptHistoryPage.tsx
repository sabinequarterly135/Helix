import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import RunHistoryTable from '@/components/history/RunHistoryTable'

export default function PromptHistoryPage() {
  const { promptId } = useParams<{ promptId: string }>()
  const { t } = useTranslation()

  if (!promptId) {
    return <p className="text-muted-foreground">{t('evolution.noPromptSelected')}</p>
  }

  return <RunHistoryTable promptId={promptId} />
}
