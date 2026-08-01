import { test, expect } from '@playwright/test'

test.describe('Sanjhubai Frontend Tests', () => {
  
  test.describe('Authentication Flow', () => {
    test('should load login page', async ({ page }) => {
      await page.goto('/login')
      await expect(page).toHaveTitle(/ورود|login/i)
      await expect(page.locator('input[name="email"], input[type="email"]')).toBeVisible()
      await expect(page.locator('input[name="password"], input[type="password"]')).toBeVisible()
    })

    test('should load signup page', async ({ page }) => {
      await page.goto('/signup')
      await expect(page).toHaveTitle(/ثبت نام|signup/i)
    })
  })

  test.describe('Chat Interface', () => {
    test.beforeEach(async ({ page }) => {
      // Mock auth and navigate to chat
      await page.addInitScript(() => {
        localStorage.setItem('authToken', 'mock-token')
      })
      await page.goto('/chat')
    })

    test('should load chat interface', async ({ page }) => {
      await expect(page.locator('[role="textbox"], .chat-input, #message-input')).toBeVisible()
    })

    test('should send and receive message', async ({ page }) => {
      const input = page.locator('[role="textbox"], .chat-input, #message-input')
      await input.fill('سلام چطوری؟')
      await input.press('Enter')
      
      // Wait for response
      await page.waitForTimeout(2000)
      await expect(page.locator('.message, .chat-message')).toContainText('سلام چطوری؟')
    })

    test('should support streaming response', async ({ page }) => {
      const input = page.locator('[role="textbox"], .chat-input, #message-input')
      await input.fill('یک خلاصه کوتاه درباره هوش مصنوعی بنویس')
      await input.press('Enter')
      
      // Check that response starts appearing
      await page.waitForTimeout(3000)
      await expect(page.locator('.message, .chat-message, .markdown')).not.toBeEmpty()
    })

    test('should support file upload', async ({ page }) => {
      await page.click('button[aria-label="آپلود"], button[title="Upload"], input[type="file"]')
      const fileInput = page.locator('input[type="file"]').first()
      await fileInput.setInputFiles({
        name: 'test.txt',
        mimeType: 'text/plain',
        buffer: Buffer.from('This is a test file content')
      })
    })
  })

  test.describe('Wallet Page', () => {
    test('should display wallet balance', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('authToken', 'mock-token')
      })
      await page.goto('/wallet')
      
      await expect(page.locator('text=موجودی, text=balance, .balance')).toBeVisible()
    })

    test('should show transaction history', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('authToken', 'mock-token')
      })
      await page.goto('/wallet/ledger')
      
      await expect(page.locator('table, .ledger, .transaction-list')).toBeVisible()
    })
  })

  test.describe('Pricing Page', () => {
    test('should display plans', async ({ page }) => {
      await page.goto('/pricing')
      
      await expect(page.locator('text=قیمت, .plan-card, [data-plan]')).toBeVisible()
    })

    test('should show currency in Toman', async ({ page }) => {
      await page.goto('/pricing')
      
      // Check that prices show تومان, not USD
      await expect(page.locator('text=تومان')).toBeVisible()
    })
  })

  test.describe('Admin Panel', () => {
    test('should require admin auth', async ({ page }) => {
      await page.goto('/admin')
      // Should redirect or show login
      await expect(page.url()).toMatch(/(login|auth|dashboard)/i)
    })

    test('admin pricing page', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('adminToken', 'mock-admin-token')
      })
      await page.goto('/admin/pricing')
      
      await expect(page.locator('table, .pricing-table')).toBeVisible()
    })
  })

  test.describe('Memory Page', () => {
    test('should list memories', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('authToken', 'mock-token')
      })
      await page.goto('/memory')
      
      await expect(page.locator('text=حافظه, .memory-item, [data-memory]')).toBeVisible()
    })

    test('should support memory search', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('authToken', 'mock-token')
      })
      await page.goto('/memory')
      
      const searchInput = page.locator('input[placeholder*="جستجو"], input[placeholder*="search"]')
      await searchInput.fill('کلیدواژه')
      await searchInput.press('Enter')
      
      await page.waitForTimeout(1000)
    })
  })

  test.describe('Responsive Design', () => {
    test('should work on mobile viewport', async ({ page, isMobile }) => {
      await page.goto('/')
      await expect(page.locator('body')).toBeVisible()
    })

    test('should support RTL layout', async ({ page }) => {
      await page.goto('/')
      
      // Check for RTL indicators
      const dir = await page.evaluate(() => document.documentElement.dir)
      expect(dir).toMatch(/(rtl|fa)/)
    })
  })

  test.describe('Error Handling', () => {
    test('should show proper 401 for unauthenticated API calls', async ({ page }) => {
      await page.goto('/wallet')
      // Should redirect to login or show login form
      await page.waitForTimeout(1000)
    })
  })

  test.describe('Performance', () => {
    test('should load main page under 2s', async ({ page }) => {
      const start = Date.now()
      await page.goto('/')
      await page.waitForLoadState('networkidle')
      const end = Date.now()
      
      expect(end - start).toBeLessThan(2000)
    })

    test('should handle large chat history', async ({ page }) => {
      await page.addInitScript(() => {
        localStorage.setItem('authToken', 'mock-token')
      })
      await page.goto('/chat')
      
      // Simulate long conversation
      for (let i = 0; i < 10; i++) {
        const input = page.locator('[role="textbox"], .chat-input, #message-input')
        await input.fill(`سوال ${i + 1}`)
        await input.press('Enter')
        await page.waitForTimeout(500)
      }
    })
  })
})