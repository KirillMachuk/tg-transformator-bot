// Dynamically import @vercel/kv to avoid module load errors
// This allows the code to work even if the package is not installed
let kv = null;
let kvImportPromise = null;

async function ensureKV() {
  if (kv !== null) return kv;
  if (kvImportPromise) return kvImportPromise;
  
  kvImportPromise = import('@vercel/kv')
    .then((module) => {
      kv = module.kv;
      console.log('[redis-store] ✓ @vercel/kv imported successfully');
      return kv;
    })
    .catch((error) => {
      console.warn('[redis-store] Failed to import @vercel/kv:', error.message);
      kv = null;
      return null;
    });
  
  return kvImportPromise;
}

/**
 * Redis-based session store for Telegraf using Vercel KV
 * Falls back to memory store if KV is not available (for local development)
 */
class RedisStore {
  constructor() {
    this.memoryStore = new Map(); // Fallback for local development
    this.useRedis = false;
    
    // Check if KV is available (Vercel environment)
    try {
      const hasUrl = !!process.env.KV_REST_API_URL;
      const hasToken = !!process.env.KV_REST_API_TOKEN;
      
      console.log('[redis-store] Initialization check:', {
        hasUrl,
        hasToken,
        urlPreview: process.env.KV_REST_API_URL ? `${process.env.KV_REST_API_URL.substring(0, 30)}...` : 'missing',
        tokenPreview: process.env.KV_REST_API_TOKEN ? `${process.env.KV_REST_API_TOKEN.substring(0, 10)}...` : 'missing'
      });
      
      if (hasUrl && hasToken) {
        // Try to import KV module asynchronously
        ensureKV().then((kvInstance) => {
          if (kvInstance) {
            this.useRedis = true;
            console.log('[redis-store] ✓ Using Vercel KV for sessions');
          } else {
            console.log('[redis-store] ⚠ @vercel/kv module not available, using memory store');
          }
        }).catch(() => {
          console.log('[redis-store] ⚠ Failed to load @vercel/kv, using memory store');
        });
        // Set useRedis optimistically - will be corrected by async import
        this.useRedis = true;
      } else {
        console.log('[redis-store] ⚠ KV not configured, using memory store (fallback)');
        console.log('[redis-store] Missing:', {
          url: !hasUrl,
          token: !hasToken
        });
      }
    } catch (error) {
      console.warn('[redis-store] KV initialization error, using memory store:', error.message);
    }
  }

  async get(key) {
    if (this.useRedis) {
      try {
        const kvInstance = await ensureKV();
        if (kvInstance) {
          const data = await kvInstance.get(key);
          return data || null;
        }
      } catch (error) {
        console.error('[redis-store] get error:', error);
        // Fallback to memory store on error
      }
    }
    return this.memoryStore.get(key) || null;
  }

  async set(key, value) {
    if (this.useRedis) {
      try {
        const kvInstance = await ensureKV();
        if (kvInstance) {
          // Set with expiration (30 days)
          await kvInstance.set(key, value, { ex: 60 * 60 * 24 * 30 });
          return;
        }
      } catch (error) {
        console.error('[redis-store] set error:', error);
        // Fallback to memory store on error
      }
    }
    this.memoryStore.set(key, value);
  }

  async delete(key) {
    if (this.useRedis) {
      try {
        const kvInstance = await ensureKV();
        if (kvInstance) {
          await kvInstance.del(key);
          return;
        }
      } catch (error) {
        console.error('[redis-store] delete error:', error);
        // Fallback to memory store on error
      }
    }
    this.memoryStore.delete(key);
  }
}

// Create singleton instance
const store = new RedisStore();

// Session middleware factory for Telegraf
export function createSessionStore() {
  return {
    get: async (key) => {
      const data = await store.get(key);
      return data;
    },
    set: async (key, value) => {
      await store.set(key, value);
    },
    delete: async (key) => {
      await store.delete(key);
    }
  };
}

export default store;

