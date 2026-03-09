export default {
  common: {
    confirm: 'Confirm',
    cancel: 'Cancel',
    save: 'Save',
    delete: 'Delete',
    edit: 'Edit',
    close: 'Close',
    loading: 'Loading...',
    error: 'Error',
    success: 'Success',
    retry: 'Retry',
    send: 'Send',
    clear: 'Clear',
    search: 'Search',
    filter: 'Filter',
    more: 'More',
    less: 'Less'
  },

  header: {
    title: 'Tableau AI Assistant',
    newSession: 'New Session',
    history: 'History',
    settings: 'Settings'
  },

  dataSource: {
    label: 'Data Source',
    placeholder: 'Select a data source',
    noDataSource: 'No data sources found',
    selectFirst: 'Please select a data source first'
  },

  input: {
    placeholder: 'Type your question...',
    send: 'Send',
    tooLong: 'Message cannot exceed {max} characters',
    empty: 'Message cannot be empty',
    boost: 'Quick Prompts'
  },

  message: {
    user: 'You',
    assistant: 'AI Assistant',
    typing: 'Typing...',
    copy: 'Copy',
    copied: 'Copied',
    feedback: 'Feedback',
    thumbsUp: 'Helpful',
    thumbsDown: 'Not Helpful',
    feedbackSubmitted: 'Thank you for your feedback'
  },

  session: {
    title: 'Sessions',
    newSession: 'New Session',
    deleteConfirm: 'Are you sure you want to delete this session?',
    rename: 'Rename',
    delete: 'Delete',
    empty: 'No sessions yet',
    loadMore: 'Load More',
    noMore: 'No more sessions'
  },

  settings: {
    title: 'Settings',
    language: 'Language',
    languageZhCN: '简体中文',
    languageEnUS: 'English',
    analysisDepth: 'Analysis Depth',
    analysisDepthQuick: 'Quick',
    analysisDepthBalanced: 'Balanced',
    analysisDepthDeep: 'Deep',
    theme: 'Theme',
    themeLight: 'Light',
    themeDark: 'Dark',
    themeAuto: 'Auto',
    showThinkingProcess: 'Show Thinking Process',
    save: 'Save Settings',
    saving: 'Saving...',
    saved: 'Settings saved'
  },

  boost: {
    title: 'Quick Prompts',
    builtin: 'Built-in Prompts',
    custom: 'Custom Prompts',
    add: 'Add Custom Prompt',
    edit: 'Edit Prompt',
    delete: 'Delete Prompt',
    titleLabel: 'Title',
    contentLabel: 'Content',
    categoryLabel: 'Category',
    categoryGeneral: 'General',
    categoryAnalysis: 'Analysis',
    categoryVisualization: 'Visualization',
    categoryData: 'Data',
    save: 'Save',
    cancel: 'Cancel'
  },

  error: {
    networkError: 'Network error, please check your connection',
    serverError: 'Server error, please try again later',
    unauthorized: 'Unauthorized, please log in again',
    forbidden: 'You do not have permission to access this resource',
    notFound: 'The requested resource was not found',
    rateLimit: 'Too many requests, please try again later',
    unknownError: 'Unknown error',
    tableauInitError: 'Failed to initialize Tableau Extension',
    loadSessionError: 'Failed to load session',
    createSessionError: 'Failed to create session',
    deleteSessionError: 'Failed to delete session',
    sendMessageError: 'Failed to send message',
    loadSettingsError: 'Failed to load settings',
    saveSettingsError: 'Failed to save settings'
  },

  empty: {
    welcome: 'Welcome to Tableau AI Assistant',
    selectDataSource: 'Please select a data source to start',
    noMessages: 'No messages yet, start a conversation',
    noSessions: 'No sessions yet'
  }
}
