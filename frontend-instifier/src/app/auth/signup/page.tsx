'use client';

import { useState } from 'react';

export default function SignupPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');

  async function handleSignup(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    try {
      const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/auth/signup`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail);
      alert('Account created successfully! Please log in.');
      window.location.href = '/auth/login';
    } catch (err: any) {
      setError(err.message);
    }
  }

  return (
    <main className="flex flex-col items-center justify-center h-screen">
      <h1 className="text-3xl font-semibold mb-4">Sign Up</h1>
      <form onSubmit={handleSignup} className="flex flex-col gap-4 w-64">
        <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" required className="p-2 border rounded" />
        <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password" required className="p-2 border rounded" />
        {error && <p className="text-red-500 text-sm">{error}</p>}
        <button type="submit" className="bg-green-600 text-white py-2 rounded">Sign Up</button>
      </form>
    </main>
  );
}
