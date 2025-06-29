'use client';

import { useEffect, useState } from 'react';

// Define Creator type matching backend fields
type Creator = {
  username: string;
  avg_reel_views: number;
  avg_story_views: number;
  follower_count: number;
  following_count: number;
  insights: string;
  price_2_story: number;
  price_reel_story: number;
  profile_pic_url: string;
  profile_url: string;
  scraped_at: string;
  source: string;
};

export default function CreatorsPage() {
  const [creators, setCreators] = useState<Creator[]>([]);
  const [loading, setLoading] = useState(true);
  const [fetchError, setFetchError] = useState<string | null>(null);

  // Filters and sorting
  const [minFollowers, setMinFollowers] = useState(0);
  const [maxFollowers, setMaxFollowers] = useState(Number.MAX_SAFE_INTEGER);
  const [minReelViews, setMinReelViews] = useState(0);
  const [minStoryViews, setMinStoryViews] = useState(0);
  const [sortField, setSortField] = useState<'follower_count' | 'following_count' | 'avg_reel_views' | 'avg_story_views'>('follower_count');
  const [sortOrder, setSortOrder] = useState<'asc' | 'desc'>('desc');

  useEffect(() => {
    const fetchCreators = async () => {
      try {
        const base = process.env.NEXT_PUBLIC_API_BASE || 'http://localhost:8000';
        const url = `${base}/creators/all`;
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data: Creator[] = await res.json();
        setCreators(data);
      } catch (err: any) {
        setFetchError(err.message || 'Unknown error');
      } finally {
        setLoading(false);
      }
    };
    fetchCreators();
  }, []);

  // Apply filters
  const filtered = creators.filter(c =>
    c.follower_count >= minFollowers &&
    c.follower_count <= maxFollowers &&
    c.avg_reel_views >= minReelViews &&
    c.avg_story_views >= minStoryViews
  );

  // Apply sorting
  const sorted = [...filtered].sort((a, b) => {
    const diff = a[sortField] - b[sortField];
    return sortOrder === 'asc' ? diff : -diff;
  });

  if (loading) return <p className="p-8">Loading creators…</p>;
  if (fetchError) return <p className="p-8 text-red-600">Error: {fetchError}</p>;
  if (!creators.length) return <p className="p-8">No creators found.</p>;

  return (
    <main className="p-8">
      <h1 className="text-2xl font-bold mb-4">Creators</h1>

      {/* Filters */}
      <div className="flex flex-wrap gap-4 mb-6">
        <div>
          <label>Min Followers:</label>
          <input
            type="number"
            value={minFollowers}
            onChange={e => setMinFollowers(Number(e.target.value))}
            className="border p-1 rounded w-24 ml-2"
          />
        </div>
        <div>
          <label>Max Followers:</label>
          <input
            type="number"
            value={maxFollowers === Number.MAX_SAFE_INTEGER ? '' : maxFollowers}
            onChange={e => setMaxFollowers(e.target.value ? Number(e.target.value) : Number.MAX_SAFE_INTEGER)}
            className="border p-1 rounded w-24 ml-2"
          />
        </div>
        <div>
          <label>Min Reel Views:</label>
          <input
            type="number"
            value={minReelViews}
            onChange={e => setMinReelViews(Number(e.target.value))}
            className="border p-1 rounded w-24 ml-2"
          />
        </div>
        <div>
          <label>Min Story Views:</label>
          <input
            type="number"
            value={minStoryViews}
            onChange={e => setMinStoryViews(Number(e.target.value))}
            className="border p-1 rounded w-24 ml-2"
          />
        </div>
        <div>
          <label>Sort By:</label>
          <select
            value={sortField}
            onChange={e => setSortField(e.target.value as any)}
            className="border p-1 rounded ml-2"
          >
            <option value="follower_count">Followers</option>
            <option value="following_count">Following</option>
            <option value="avg_reel_views">Avg Reel Views</option>
            <option value="avg_story_views">Avg Story Views</option>
          </select>
        </div>
        <div>
          <label>Order:</label>
          <select
            value={sortOrder}
            onChange={e => setSortOrder(e.target.value as any)}
            className="border p-1 rounded ml-2"
          >
            <option value="desc">Descending</option>
            <option value="asc">Ascending</option>
          </select>
        </div>
      </div>

      {/* List View */}
      <ul className="divide-y">
        {sorted.map((c, i) => (
          <li key={i} className="py-4 flex items-center space-x-4">
            <img
              src={c.profile_pic_url}
              alt={c.username}
              className="w-12 h-12 rounded-full flex-shrink-0"
              onError={e => { (e.currentTarget as HTMLImageElement).src = 'https://via.placeholder.com/48'; }}
            />
            <div className="flex-1">
              <a
                href={c.profile_url}
                target="_blank"
                rel="noopener noreferrer"
                className="font-semibold text-lg"
              >
                {c.username}
              </a>
              <div className="text-sm text-gray-600 mt-1">
                Followers: {c.follower_count.toLocaleString()} •
                Following: {c.following_count.toLocaleString()} •
                Reel Avg: {c.avg_reel_views.toLocaleString()} •
                Story Avg: {c.avg_story_views.toLocaleString()}
              </div>
            </div>
          </li>
        ))}
      </ul>
    </main>
  );
}
