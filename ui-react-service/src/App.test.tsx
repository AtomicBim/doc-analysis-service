import React from 'react';
import { render, screen } from '@testing-library/react';
import App from './App';

test('renders document analysis app header', () => {
  render(<App />);
  const headerElement = screen.getByText(/Анализ проектной документации/i);
  expect(headerElement).toBeInTheDocument();
});
