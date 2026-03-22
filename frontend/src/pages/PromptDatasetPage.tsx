import { useParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { CaseList } from '@/components/datasets/CaseList'

export default function PromptDatasetPage() {
  const { promptId } = useParams<{ promptId: string }>()
  const { t } = useTranslation()

  if (!promptId) {
    return <p className="text-muted-foreground">{t('evolution.noPromptSelected')}</p>
  }

  return <CaseList promptId={promptId} />
}
