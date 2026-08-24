'use client'

import { useAuth } from '@/lib/auth'
import { useUsageData } from './hooks/useUsageData'
import { UsageHeader } from './components/UsageHeader'
import { UnauthenticatedUsage } from './components/UnauthenticatedUsage'
import { UsageLoadingSkeleton } from './components/UsageLoadingSkeleton'
import { UsageEmptyState } from './components/UsageEmptyState'
import { SummaryCards } from './components/SummaryCards'
import { MostExpensiveCard } from './components/MostExpensiveCard'
import { ModelDistributionCard } from './components/ModelDistributionCard'
import { ModelBreakdownCard } from './components/ModelBreakdownCard'
import { RecentEventsTable } from './components/RecentEventsTable'

/* ═══════════════════════════════════════════════════════════════════════════
   Main Page

   State/logic is split across hooks/ (data fetching + derived stats) and
   components/ (skeletons, summary/chart/table cards) -- this file wires
   them together and owns only the page-wide layout.
   ═══════════════════════════════════════════════════════════════════════════ */

export default function UsagePage() {
  const { token, user, loading: authLoading } = useAuth()
  const {
    data,
    loading,
    refreshing,
    fetchUsage,
    exportCsv,
    mostExpensive,
    modelStats,
    totalModelCost,
    donutData,
    totalTokens,
    maxModelCost,
    hasAnyData,
    recentEvents,
  } = useUsageData(token)

  if (authLoading) return null

  if (!user) {
    return <UnauthenticatedUsage />
  }

  return (
    <div style={{ maxWidth: 1000, margin: '0 auto', padding: '32px 20px 64px' }} className="usage-page">
      <UsageHeader
        hasAnyData={hasAnyData}
        refreshing={refreshing}
        onExport={exportCsv}
        onRefresh={() => fetchUsage(true)}
      />

      {loading ? (
        <UsageLoadingSkeleton />
      ) : !hasAnyData ? (
        <UsageEmptyState />
      ) : (
        <>
          <SummaryCards data={data} totalTokens={totalTokens} />

          <MostExpensiveCard mostExpensive={mostExpensive} />

          <ModelDistributionCard
            modelStats={modelStats}
            totalModelCost={totalModelCost}
            donutData={donutData}
          />

          <ModelBreakdownCard
            hasBreakdown={(data?.per_model_breakdown.length ?? 0) > 0}
            modelStats={modelStats}
            maxModelCost={maxModelCost}
          />

          <RecentEventsTable recentEvents={recentEvents} />
        </>
      )}
    </div>
  )
}
