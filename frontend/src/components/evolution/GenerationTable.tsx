import { useTranslation } from 'react-i18next'
import type { GenerationData } from '../../types/evolution'
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card'
import { Table, TableHeader, TableBody, TableRow, TableHead, TableCell } from '@/components/ui/table'

interface GenerationTableProps {
  data: GenerationData[]
  isLive?: boolean
}

export default function GenerationTable({ data, isLive = false }: GenerationTableProps) {
  const { t } = useTranslation()
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{t('evolution.generationDetails')}</CardTitle>
      </CardHeader>
      <CardContent>
        {data.length === 0 ? (
          <div className="flex items-center justify-center py-12 gap-2">
            {isLive && (
              <span className="relative flex h-2 w-2">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
              </span>
            )}
            <p className="text-muted-foreground">{isLive ? t('evolution.evaluatingCandidates') : t('evolution.waitingForData')}</p>
          </div>
        ) : (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t('evolution.generation')}</TableHead>
                <TableHead>{t('evolution.bestFitness')}</TableHead>
                <TableHead>{t('evolution.avgFitness')}</TableHead>
                <TableHead>{t('evolution.bestNorm')}</TableHead>
                <TableHead>{t('evolution.avgNorm')}</TableHead>
                <TableHead>{t('evolution.candidates')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {data.map((gen) => (
                <TableRow key={gen.generation}>
                  <TableCell>{gen.label}</TableCell>
                  <TableCell>{Number(gen.bestFitness ?? 0).toFixed(4)}</TableCell>
                  <TableCell>{Number(gen.avgFitness ?? 0).toFixed(4)}</TableCell>
                  <TableCell>{Number(gen.bestNormalized ?? 0).toFixed(4)}</TableCell>
                  <TableCell>{Number(gen.avgNormalized ?? 0).toFixed(4)}</TableCell>
                  <TableCell>{gen.candidatesEvaluated}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  )
}
