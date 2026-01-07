#!/usr/bin/env pwsh
# Audit script to check all prompt templates for required placeholders

$promptsFile = "c:\Users\trial\projects\my git\mixed-questions-\prompts.yaml"
$content = Get-Content $promptsFile -Raw

# Define all templates
$templates = @(
    "assertion_reasoning",
    "assertion_reasoning_pdf",
    "case_study_maths",
    "case_study_maths_pdf",
    "descriptive",
    "descriptive_pdf",
    "descriptive_subq",
    "descriptive_subq_pdf",
    "FIB",
    "FIB_pdf",
    "mcq_questions",
    "mcq_questions_pdf",
    "multi_part_maths",
    "multi_part_maths_pdf"
)

# Required placeholders
$requiredPlaceholders = @("{{Old_Concept}}", "{{Additional_Notes}}")

Write-Host "=== PROMPT TEMPLATE PLACEHOLDER AUDIT ===" -ForegroundColor Cyan
Write-Host ""

$issues = @()

foreach ($template in $templates) {
    # Find template start and end
    $pattern = "(?ms)^$template\s*:\s*\|(.*?)(?=^[a-z_]+\s*:\s*\||$)"
    $match = [regex]::Match($content, $pattern)
    
    if ($match.Success) {
        $templateContent = $match.Groups[1].Value
        $missing = @()
        
        foreach ($placeholder in $requiredPlaceholders) {
            if ($templateContent -notmatch [regex]::Escape($placeholder)) {
                $missing += $placeholder
            }
        }
        
        if ($missing.Count -gt 0) {
            Write-Host "❌ $template" -ForegroundColor Red
            Write-Host "   Missing: $($missing -join ', ')" -ForegroundColor Yellow
            $issues += [PSCustomObject]@{
                Template = $template
                Missing = $missing -join ', '
            }
        } else {
            Write-Host "✅ $template" -ForegroundColor Green
        }
    } else {
        Write-Host "⚠️  $template - NOT FOUND" -ForegroundColor Magenta
    }
}

Write-Host ""
Write-Host "=== SUMMARY ===" -ForegroundColor Cyan
Write-Host "Total templates: $($templates.Count)"
Write-Host "Templates with issues: $($issues.Count)" -ForegroundColor $(if ($issues.Count -gt 0) { "Red" } else { "Green" })

if ($issues.Count -gt 0) {
    Write-Host ""
    Write-Host "Issues found:" -ForegroundColor Yellow
    $issues | Format-Table -AutoSize
}
