# Feature Request: Allow Relative Date Filters to Reference Calculated Fields Defined in Query

## Summary
Enable VizQL Data Service API to allow Relative Date Filters (filterType: DATE) to reference calculated fields defined in the same query's `fields` array by their `fieldCaption`.

## Current Behavior
When using the VizQL Data Service API (`/query-datasource`), users can define calculated fields in the `fields` array with a custom `fieldCaption`. However, these calculated fields cannot be referenced in filters.

**Example that fails:**
```json
{
  "fields": [
    {
      "fieldCaption": "ParsedDate",
      "calculation": "DATEPARSE('yyyy-MM-dd', [StringDateField])"
    },
    {"fieldCaption": "Sales", "function": "SUM"}
  ],
  "filters": [
    {
      "filterType": "DATE",
      "field": {"fieldCaption": "ParsedDate"},
      "periodType": "YEARS",
      "dateRangeType": "CURRENT"
    }
  ]
}
```

**Error:** `Unknown Field: ParsedDate`

## Expected Behavior
Allow filters to reference calculated fields defined in the `fields` array by their `fieldCaption`:

```json
{
  "fields": [
    {"fieldCaption": "ParsedDate", "calculation": "DATEPARSE('yyyy-MM-dd', [StringField])"}
  ],
  "filters": [
    {
      "filterType": "DATE",
      "field": {"fieldCaption": "ParsedDate"},  // Reference the calculated field defined above
      "periodType": "YEARS",
      "dateRangeType": "CURRENT"
    }
  ]
}
```

This is consistent with how Tableau Desktop works - you can create a calculated field and then use it in filters.

## Use Case
Many data sources store dates as strings (e.g., "2024-01-15" in a VARCHAR column). Users need to:
1. Convert these strings to dates using `DATEPARSE()`
2. Apply relative date filters (e.g., "Current Year", "Last 30 Days")

Currently, the only workaround is to use `QUANTITATIVE_DATE` with hardcoded date ranges, which defeats the purpose of relative date filtering.

## Current Workaround
Use `QUANTITATIVE_DATE` filter with dynamically calculated date ranges in the application layer:
```json
{
  "filterType": "QUANTITATIVE_DATE",
  "field": {"calculation": "DATEPARSE('yyyy-MM-dd', [StringField])"},
  "quantitativeFilterType": "RANGE",
  "minDate": "2025-01-01",  // Calculated in application
  "maxDate": "2025-12-31"   // Calculated in application
}
```

This works but requires the application to calculate date ranges, losing the elegance of relative date filters.

## Impact
- Improves API consistency with Tableau Desktop behavior
- Enables more flexible date filtering scenarios
- Reduces application-side complexity for common use cases
- Allows calculated fields defined in `fields` to be reused in `filters`

## Environment
- VizQL Data Service API version: 20261.0
- Tested on: Tableau Cloud

## Related
- In Tableau Desktop, you can create a calculated field and use it in filters
- The VizQL Data Service API should support the same workflow
- Currently, `fields` and `filters` have separate namespaces and cannot reference each other

---

**Submitted by:** [天赐]
**Date:** December 17, 2025
