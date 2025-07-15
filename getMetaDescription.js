// getMetaDescription.js - Enhanced version with full article content extraction
import fetch from 'node-fetch';
import * as cheerio from 'cheerio';

// Enhanced content extraction for better article summaries
export async function getFullArticleContent(url) {
  try {
    console.log(`📖 Fetching full content from: ${url}`);
    
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
      }
    });
    
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    
    const html = await res.text();
    const $ = cheerio.load(html);
    
    // Remove unwanted elements
    $('script, style, nav, header, footer, aside, .advertisement, .ad, .social-share').remove();
    
    // Try multiple selectors for article content
    const contentSelectors = [
      'article .article-body',
      'article .story-body',
      'article .entry-content',
      'article .post-content',
      'article .content',
      'article p',
      '.article-content',
      '.story-content',
      '.entry-content',
      '.post-body',
      '.content-body',
      'main article',
      'main .content',
      '[data-module="ArticleBody"]',
      '.RichTextStoryBody',
      '.ArticleBody',
      '.story-body__inner'
    ];
    
    let extractedContent = '';
    
    for (const selector of contentSelectors) {
      const elements = $(selector);
      if (elements.length > 0) {
        // Extract text from paragraphs
        const paragraphs = [];
        
        elements.find('p').each((i, elem) => {
          const text = $(elem).text().trim();
          if (text.length > 50 && !text.includes('Subscribe') && !text.includes('Click here')) {
            paragraphs.push(text);
          }
        });
        
        if (paragraphs.length > 0) {
          extractedContent = paragraphs.slice(0, 3).join(' '); // First 3 paragraphs
          break;
        }
      }
    }
    
    // If no article content found, try getting first few paragraphs from anywhere
    if (!extractedContent) {
      const allParagraphs = [];
      $('p').each((i, elem) => {
        const text = $(elem).text().trim();
        if (text.length > 50 && 
            !text.includes('Subscribe') && 
            !text.includes('Click here') && 
            !text.includes('Follow us') &&
            !text.includes('Advertisement') &&
            !text.includes('Sign up')) {
          allParagraphs.push(text);
        }
      });
      
      if (allParagraphs.length > 0) {
        extractedContent = allParagraphs.slice(0, 2).join(' '); // First 2 good paragraphs
      }
    }
    
    // Clean up the content
    if (extractedContent) {
      extractedContent = extractedContent
        .replace(/\s+/g, ' ')
        .replace(/\n+/g, ' ')
        .trim();
      
      // Limit length for processing
      if (extractedContent.length > 800) {
        extractedContent = extractedContent.substring(0, 800) + '...';
      }
      
      console.log(`✅ Extracted ${extractedContent.length} characters of content`);
      return extractedContent;
    }
    
    console.log(`⚠️ No substantial content found for ${url}`);
    return null;
    
  } catch (error) {
    console.warn(`⚠️ Failed to fetch full content for ${url}: ${error.message}`);
    return null;
  }
}

// Original meta description function (kept for fallback)
export async function getMetaDescription(url) {
  try {
    const res = await fetch(url, {
      headers: {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
      }
    });
    
    if (!res.ok) {
      throw new Error(`HTTP ${res.status}`);
    }
    
    const html = await res.text();
    const $ = cheerio.load(html);
    
    // Try different meta description sources in order of preference
    const sources = [
      'meta[property="og:description"]',
      'meta[name="description"]',
      'meta[name="Description"]',
      'meta[property="description"]',
      'meta[name="twitter:description"]'
    ];
    
    for (const source of sources) {
      const content = $(source).attr('content');
      if (content && content.length > 50) {
        return content.trim();
      }
    }
    
    // Fallback to first substantial paragraph
    const firstParagraph = $('article p, .article-body p, .story-body p').first().text().trim();
    if (firstParagraph && firstParagraph.length > 50) {
      return firstParagraph.length > 300 ? firstParagraph.substring(0, 300) + '...' : firstParagraph;
    }
    
    // Last resort - any paragraph
    const anyParagraph = $('p').first().text().trim();
    if (anyParagraph && anyParagraph.length > 50) {
      return anyParagraph.length > 300 ? anyParagraph.substring(0, 300) + '...' : anyParagraph;
    }
    
    return null;
    
  } catch (error) {
    console.warn(`⚠️ Failed to fetch meta description for ${url}: ${error.message}`);
    return null;
  }
}

// Analyze article sentiment and key topics for better categorization
export function analyzeArticleContent(title, description, content) {
  const fullText = `${title} ${description} ${content || ''}`.toLowerCase();
  
  const analysis = {
    sentiment: 'neutral',
    topics: [],
    urgency: 'low',
    playerMentions: [],
    teamMentions: []
  };
  
  // Sentiment analysis keywords
  const positiveWords = ['win', 'victory', 'champion', 'record', 'success', 'breakthrough', 'comeback'];
  const negativeWords = ['loss', 'injury', 'suspend', 'fine', 'controversy', 'struggle', 'disappoint'];
  
  const positiveCount = positiveWords.filter(word => fullText.includes(word)).length;
  const negativeCount = negativeWords.filter(word => fullText.includes(word)).length;
  
  if (positiveCount > negativeCount) {
    analysis.sentiment = 'positive';
  } else if (negativeCount > positiveCount) {
    analysis.sentiment = 'negative';
  }
  
  // Topic identification
  const topics = {
    'trades': ['trade', 'deal', 'acquire', 'sign', 'contract'],
    'injuries': ['injury', 'hurt', 'strain', 'tear', 'surgery'],
    'games': ['game', 'match', 'score', 'final', 'defeat'],
    'playoffs': ['playoff', 'championship', 'finals', 'postseason'],
    'personnel': ['coach', 'manager', 'hire', 'fire', 'retire']
  };
  
  Object.entries(topics).forEach(([topic, keywords]) => {
    if (keywords.some(keyword => fullText.includes(keyword))) {
      analysis.topics.push(topic);
    }
  });
  
  // Urgency assessment
  const urgentWords = ['breaking', 'urgent', 'just in', 'developing', 'alert'];
  if (urgentWords.some(word => fullText.includes(word))) {
    analysis.urgency = 'high';
  }
  
  return analysis;
}