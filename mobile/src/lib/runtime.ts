import AsyncStorage from '@react-native-async-storage/async-storage';
import * as Crypto from 'expo-crypto';
import { Api } from '../core/api';
import { Outbox } from '../core/outbox';
import { SyncEngine } from '../core/sync';
import { API_URL } from './config';
import { supabase } from './supabase';

export const outbox = new Outbox(AsyncStorage);
export const api = new Api(API_URL, async () => (await supabase.auth.getSession()).data.session?.access_token ?? null);
export const engine = new SyncEngine(outbox, api);
export const newId = () => Crypto.randomUUID();
