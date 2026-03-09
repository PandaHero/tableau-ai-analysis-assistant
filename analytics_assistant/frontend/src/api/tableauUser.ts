function getCachedUsername(): string | null {
  try {
    return window.tableau?.extensions?.settings?.get('tableau_username') || null
  } catch {
    return null
  }
}

export function getTableauUsername(): string {
  if (typeof window === 'undefined') {
    return 'tableau_user'
  }

  const uniqueUserId = window.tableau?.extensions?.environment?.uniqueUserId
  if (uniqueUserId) {
    return uniqueUserId
  }

  return getCachedUsername() || 'tableau_user'
}
