/** Uzbek (Latin) UI dictionary. Untranslated keys fall back to Russian. */
const uz = {
  common: {
    add: "Qo'shish", all: 'Hammasi', archive: 'Arxivga', archived: 'Arxiv', back: 'Orqaga', cancel: 'Bekor qilish', comment: 'Izoh',
    confirm: 'Tasdiqlash', create: 'Yaratish', delete: "O'chirish", department: "Bo'lim", description: 'Tavsif', edit: 'Tahrirlash',
    export: 'Eksport', name: 'Nomi', next: 'Keyingi', no: "Yo'q", reason: 'Sabab', refresh: 'Yangilash', region: 'Hudud',
    required: 'Majburiy maydon', responsible: "Mas'ul", restore: 'Tiklash', save: 'Saqlash', saved: 'Saqlandi', search: 'Qidirish',
    select: 'Tanlang', status: 'Holat', toHome: 'Bosh sahifaga', total: 'Jami: {{count}}', yes: 'Ha', backdated: 'Orqa sana bilan',
  },
  menu: {
    dashboard: 'Bosh sahifa', employees: 'Xodimlar', assetsGroup: 'Uskunalar', assets: 'Aktivlar', operations: 'Operatsiyalar',
    repairs: "Ta'mirlash", inventory: 'Inventarizatsiya', stock: 'Sarf materiallari ombori', contracts: 'Shartnomalar',
    licensesGroup: "Dasturlar va ruxsatlar", licenses: 'Litsenziyalar', software: 'Dasturlar katalogi', access: 'Ruxsatlar',
    lifecycle: 'Hayot sikli', onboarding: 'Ishga qabul', offboarding: "Ishdan bo'shatish", documents: 'Hujjatlar', reports: 'Hisobotlar',
    import: 'Import', notifications: 'Bildirishnomalar', admin: "Ma'muriyat", dictionaries: "Ma'lumotnomalar", customFields: "Qo'shimcha maydonlar",
    templates: 'Hujjat shablonlari', checklistTemplates: 'Nazorat varaqasi shablonlari', users: 'Foydalanuvchilar', roles: 'Rollar va huquqlar',
    audit: 'Audit jurnali', settings: 'Sozlamalar', backup: 'Zaxira nusxalar', system: 'Tizim haqida',
  },
  header: { searchPlaceholder: 'Qidirish: inventar raqami, seriya raqami, F.I.Sh…', quickActions: 'Tezkor amallar', profile: 'Profil', logout: 'Chiqish', darkTheme: "Qorong'i mavzu", lightTheme: "Yorug' mavzu" },
  quick: { addEmployee: "Xodim qo'shish", addAsset: "Aktiv qo'shish", issue: 'Uskuna berish', return: 'Qaytarib olish', transfer: 'Uskunani topshirish', repair: "Ta'mirga yuborish", document: 'Hujjat yaratish' },
  login: { subtitle: 'IT aktivlarini hisobga olish', userName: 'Login', password: 'Parol', submit: 'Kirish' },
  dashboard: { title: 'Bosh sahifa', welcome: 'Xush kelibsiz, {{name}}', allRegions: 'Barcha hududlar', recentOperations: "So'nggi operatsiyalar", expiring: 'Muddati tugayotganlar' },
  employees: { new: 'Yangi xodim', fullName: 'F.I.Sh.', position: 'Lavozim', phone: 'Telefon', hireDate: 'Ishga qabul sanasi', terminationDate: "Bo'shatish sanasi" },
  assets: {
    new: 'Yangi aktiv', inventoryNumber: 'Inventar raqami', name: 'Nomi', type: 'Turi', model: 'Model', serialNumber: 'Seriya raqami', location: 'Joylashuv', employee: 'Xodim',
    actions: { issue: 'Berish', return: 'Qabul qilish', transfer: 'Topshirish', repair: "Ta'mirga", status: "Holatni o'zgartirish" },
  },
  operations: { effectiveAt: 'Operatsiya sanasi va vaqti', issueTitle: 'Uskuna berish', returnTitle: 'Uskunani qabul qilish', transferTitle: 'Uskunani topshirish', type: 'Turi', employee: 'Xodim' },
  tabs: { overview: 'Umumiy', history: 'Tarix', timeline: 'Xronologiya', documents: 'Hujjatlar', attachments: 'Fayllar', audit: 'Audit' },
  enums: {
    assetKind: { InStock: 'Omborda', Assigned: 'Berilgan', Reserved: 'Band qilingan', InRepair: "Ta'mirda", Lost: "Yo'qolgan", WrittenOff: 'Hisobdan chiqarilgan', Archived: 'Arxiv' },
    employeeKind: { Active: 'Ishlaydi', Leave: "Ta'tilda", Terminated: "Bo'shatilgan", Archived: 'Arxiv' },
    operation: { Issue: 'Berish', Return: 'Qaytarish', Transfer: 'Topshirish', StatusChange: "Holat o'zgarishi", Repair: "Ta'mirlash" },
  },
  errors: { generic: 'Xatolik', NOT_FOUND: 'Topilmadi', FORBIDDEN: "Huquq yetarli emas", INVALID_CREDENTIALS: "Login yoki parol noto'g'ri" },
};

export default uz;
