'use client';

import { useEffect, useState } from 'react';

export default function Dashboard() {
  const [userEmail, setUserEmail] = useState('');
  const [creators, setCreators] = useState<any[]>([]);

  useEffect(() => {
    const token = localStorage.getItem('token');
    if (!token) {
      window.location.href = '/auth/login';
      return;
    }
    setUserEmail('user@example.com');

    fetch(`${process.env.NEXT_PUBLIC_API_BASE}/creators/all`)
      .then((res) => res.json())
      .then(setCreators);
  }, []);

  return (
    <main className="p-8">
      <h1 className="text-3xl font-semibold mb-4">Dashboard</h1>
      <p className="mb-6">Welcome, {userEmail}!</p>

      <div className="mb-4">
        <a href="/creators" className="bg-blue-500 text-white px-4 py-2 rounded">View All Creators</a>
      </div>

      <h2 className="text-xl font-semibold mb-2">All Creators</h2>
      <ul className="space-y-2">
        {creators.map((creator, i) => (
          <li key={i} className="p-3 border rounded shadow">
            <p className="font-bold">{creator.name}</p>
            <p className="text-sm text-gray-600">{creator.category}</p>
          </li>
        ))}
      </ul>
    </main>
  );
}