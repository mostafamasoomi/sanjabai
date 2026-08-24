import { useState, useEffect, useCallback } from 'react'
import { loadFavorites, saveFavorites } from '../onboardingHelpers'

/** Loads/persists the user's favorite model ids in localStorage across the
    onboarding flow (step 2 picks favorites, step 3 uses them for the
    recommendation, and `finish()` on the page saves them one last time). */
export function useFavorites() {
  const [favoriteIds, setFavoriteIds] = useState<string[]>([])

  // Load saved favorites on mount
  useEffect(() => {
    setFavoriteIds(loadFavorites())
  }, [])

  // Persist favorites whenever they change
  useEffect(() => {
    if (favoriteIds.length > 0) {
      saveFavorites(favoriteIds)
    }
  }, [favoriteIds])

  const toggleFavorite = useCallback((id: string) => {
    setFavoriteIds((prev) => {
      if (prev.includes(id)) return prev.filter((x) => x !== id)
      return [...prev, id]
    })
  }, [])

  return { favoriteIds, toggleFavorite }
}
